import pytest

from faultsense.embeddings import BgeM3Embedder

pytestmark = pytest.mark.models


def test_bge_m3_ranks_a_paraphrase_above_an_unrelated_text():
    vectors = BgeM3Embedder().embed([
        "The drive trips on hot afternoons",
        "Device temperature too high",
        "Modbus communication interruption",
    ])
    assert vectors.shape == (3, 1024)
    assert float(vectors[0] @ vectors[1]) > float(vectors[0] @ vectors[2])
