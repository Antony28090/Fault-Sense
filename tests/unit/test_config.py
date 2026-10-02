from faultsense.config import Settings


def test_defaults_without_env_file(monkeypatch):
    for var in ("DATABASE_URL", "LLM_MODEL", "EVIDENCE_THRESHOLD", "DEVICE"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "anthropic"
    assert settings.llm_model == "claude-opus-5-5"
    assert settings.llm_effort == "high"
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.reranker_model == "BAAI/bge-reranker-v2-m3"
    assert settings.evidence_threshold == 0.14
    assert settings.cause_match_threshold == 0.65
    assert settings.db_schema == "public"
    assert settings.manuals_dir.name == "manuals"
    assert settings.processed_dir.name == "processed"


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("EVIDENCE_THRESHOLD", "0.45")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-5-5")
    settings = Settings(_env_file=None)
    assert settings.evidence_threshold == 0.45
    assert settings.llm_model == "claude-sonnet-5-5"


def test_query_rewrite_defaults_on_with_low_effort():
    settings = Settings(_env_file=None)
    assert settings.query_rewrite is True
    assert settings.rewrite_effort == "low"
