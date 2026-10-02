from faultsense.llm.base import LLMError
from faultsense.llm.fake import FakeLLM
from faultsense.retrieval.rewrite import REWRITE_SYSTEM, QueryRewriter


def test_rewriter_returns_the_models_search_query():
    llm = FakeLLM([{"search_query": "Drive trips on device overheating at high ambient temperature"}])
    rewritten = QueryRewriter(llm).rewrite("pump trips on hot afternoons")
    assert rewritten == "Drive trips on device overheating at high ambient temperature"
    assert llm.calls[0]["system"] == REWRITE_SYSTEM
    assert llm.calls[0]["user"] == "pump trips on hot afternoons"


def test_rewriter_falls_back_to_none_on_llm_failure_or_empty_answer():
    assert QueryRewriter(FakeLLM([LLMError("down")])).rewrite("q") is None
    assert QueryRewriter(FakeLLM([{"search_query": "   "}])).rewrite("q") is None


def test_rewrite_instructions_forbid_guessing_codes():
    assert "verbatim" in REWRITE_SYSTEM and "Never explain or guess" in REWRITE_SYSTEM


def test_rewriter_ignores_replies_that_are_not_json_objects():
    assert QueryRewriter(FakeLLM([["device overheating"]])).rewrite("q") is None
    assert QueryRewriter(FakeLLM(["device overheating"])).rewrite("q") is None
