"""Cross-encoder reranking (bge-reranker-v2-m3, multilingual) and a test double."""
from __future__ import annotations

import re
from typing import Protocol


class Reranker(Protocol):
    def score(self, query: str, passages: list[str]) -> list[float]: ...


class BgeReranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", device: str = "cuda",
                 max_length: int = 1024, batch_size: int = 16):
        import torch
        from sentence_transformers import CrossEncoder

        from faultsense.embeddings import resolve_device

        self.device = resolve_device(device)
        self._model = CrossEncoder(model_name, device=self.device, max_length=max_length,
                                   activation_fn=torch.nn.Sigmoid())
        if self.device.startswith("cuda"):
            self._model.half()
        self._batch_size = batch_size

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        scores = self._model.predict([(query, p) for p in passages], batch_size=self._batch_size,
                                     show_progress_bar=False)
        return [float(s) for s in scores]


class OverlapReranker:
    """Test double: the share of query words that appear in the passage."""

    def score(self, query: str, passages: list[str]) -> list[float]:
        words = set(re.findall(r"[a-z0-9]+", query.lower()))
        return [
            len(words & set(re.findall(r"[a-z0-9]+", p.lower()))) / max(len(words), 1)
            for p in passages
        ]
