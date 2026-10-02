from faultsense.config import Settings
from faultsense.retrieval.rewrite import QueryRewriter
from faultsense.wiring import build_rewriter


def test_rewriter_uses_the_low_effort_setting():
    rewriter = build_rewriter(Settings(_env_file=None, llm_api_key="test-key", llm_effort="high"))
    assert isinstance(rewriter, QueryRewriter)
    assert rewriter._llm._effort == "low"


def test_rewriter_can_be_switched_off():
    assert build_rewriter(Settings(_env_file=None, llm_api_key="test-key", query_rewrite=False)) is None


def test_components_reconnect_to_the_database_after_a_dropped_connection(monkeypatch):
    import psycopg

    from faultsense import wiring

    class Conn:
        def __init__(self, alive):
            self.alive = alive

        def execute(self, sql, params=None):
            if not self.alive:
                raise psycopg.OperationalError("server closed the connection unexpectedly")
            return type("Cursor", (), {"fetchall": lambda self: [("atv12", "abc")]})()

        def close(self):
            pass

    opened = []

    def fake_connect(url, schema):
        opened.append((url, schema))
        return Conn(alive=len(opened) > 1)

    monkeypatch.setattr(wiring, "connect", fake_connect)
    monkeypatch.setattr(wiring, "BgeM3Embedder", lambda *args: object())
    monkeypatch.setattr(wiring, "BgeReranker", lambda *args: object())
    settings = Settings(_env_file=None, database_url="postgresql://db", db_schema="mm", query_rewrite=False)
    components = wiring.build_components(settings)
    assert components.repo.manual_hashes() == {"atv12": "abc"}
    assert opened == [("postgresql://db", "mm"), ("postgresql://db", "mm")]


def test_rewriter_can_use_a_different_model_from_the_diagnosis():
    from faultsense.llm.anthropic_provider import AnthropicProvider
    from faultsense.llm.ollama_provider import OllamaProvider

    local = dict(_env_file=None, llm_api_key="test-key", llm_provider="ollama", llm_model="qwen3.5:4b")
    assert isinstance(build_rewriter(Settings(**local))._llm, OllamaProvider)
    hybrid = build_rewriter(Settings(**local, rewrite_provider="anthropic", rewrite_model="claude-sonnet-5-5"))
    assert isinstance(hybrid._llm, AnthropicProvider)
    assert (hybrid._llm._model, hybrid._llm._effort) == ("claude-sonnet-5-5", "low")


def test_catalog_lists_machines_manual_files_and_models():
    from faultsense.wiring import build_catalog

    settings = Settings(_env_file=None, llm_provider="ollama", llm_model="qwen3.5:4b",
                        rewrite_provider="anthropic", rewrite_model="claude-sonnet-5-5")
    catalog = build_catalog(settings)
    pump = next(m for m in catalog.machines if m["id"] == "DEMO-PUMP-01")
    assert (pump["manual"], pump["family"]) == ("atv600", "ATV600")
    assert catalog.manual_files["atv600"].parent == settings.manuals_dir
    assert catalog.manual_files["atv600"].suffix.lower() == ".pdf"
    assert catalog.engine == {"diagnosis": "ollama qwen3.5:4b", "rewrite": "anthropic claude-sonnet-5-5"}
    off = build_catalog(Settings(_env_file=None, query_rewrite=False, llm_model="claude-sonnet-5-5"))
    assert off.engine == {"diagnosis": "anthropic claude-sonnet-5-5", "rewrite": None}
