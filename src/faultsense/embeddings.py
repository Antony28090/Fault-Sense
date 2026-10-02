"""Text embedders: bge-m3 for real use (multilingual, so Phase 2 needs no re-indexing) and a
hashing embedder for tests."""
from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np

EMBEDDING_DIM = 1024


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


def resolve_device(device: str) -> str:
    if device.startswith("cuda"):
        import torch

        if not torch.cuda.is_available():
            return "cpu"
    return device


class BgeM3Embedder:
    dim = EMBEDDING_DIM

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = "cuda",
                 max_seq_length: int = 1024, batch_size: int = 16):
        from sentence_transformers import SentenceTransformer

        self.device = resolve_device(device)
        self._model = SentenceTransformer(model_name, device=self.device)
        if self.device.startswith("cuda"):
            self._model.half()
        self._model.max_seq_length = max_seq_length
        self._batch_size = batch_size

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(
            list(texts), batch_size=self._batch_size, normalize_embeddings=True,
            convert_to_numpy=True, show_progress_bar=len(texts) > 64,
        )
        return np.asarray(vectors, dtype=np.float32)


class HashEmbedder:
    """Deterministic bag-of-words vectors so tests run without model weights."""

    def __init__(self, dim: int = EMBEDDING_DIM):
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                out[row, int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
            norm = np.linalg.norm(out[row])
            if norm:
                out[row] /= norm
        return out
