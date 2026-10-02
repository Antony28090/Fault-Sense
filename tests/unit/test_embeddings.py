import numpy as np

from faultsense.embeddings import HashEmbedder


def test_hash_embedder_is_normalised_and_deterministic():
    embedder = HashEmbedder()
    a, b, c = embedder.embed(["drive overheating fan", "drive overheating fan", "modbus link lost"])
    assert a.shape == (1024,)
    assert np.isclose(np.linalg.norm(a), 1.0)
    assert np.allclose(a, b)
    assert float(a @ c) < float(a @ b)
