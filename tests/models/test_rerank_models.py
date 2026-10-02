import pytest

from faultsense.retrieval.rerank import BgeReranker

pytestmark = pytest.mark.models


def test_bge_reranker_prefers_the_relevant_passage():
    scores = BgeReranker().score(
        "drive trips on hot afternoons",
        ["Device temperature too high. Ambient temperature too high.", "Modbus communication interruption."],
    )
    assert 0.0 <= min(scores) and max(scores) <= 1.0
    assert scores[0] > scores[1]
