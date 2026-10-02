"""Exact fault-code lookup + keyword + vector search, fused (RRF) and reranked."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from faultsense.codes import code_key, confusable_variants, query_code_candidates
from faultsense.db.repository import FaultHit, StoredChunk
from faultsense.embeddings import Embedder
from faultsense.retrieval.fusion import rrf
from faultsense.retrieval.rerank import Reranker


class SearchBackend(Protocol):
    def fault_index(self) -> dict[str, list[FaultHit]]: ...
    def keyword_search(self, query: str, manual_ids: list[str] | None, limit: int) -> list[tuple[str, float]]: ...
    def vector_search(self, embedding, manual_ids: list[str] | None, limit: int,
                      kind: str | None = None) -> list[tuple[str, float]]: ...
    def get_chunks(self, ids: Sequence[str]) -> dict[str, StoredChunk]: ...


class Rewriter(Protocol):
    def rewrite(self, query: str) -> str | None: ...


@dataclass(frozen=True)
class CodeMatch:
    hit: FaultHit
    token: str  # what the operator typed
    fuzzy: bool  # matched only through a display look-alike (O/0, I/1, S/5)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: StoredChunk
    score: float  # reranker score in [0, 1]; exact code hits get 1.0
    code: str | None = None


@dataclass
class RetrievalResult:
    query: str
    manual_ids: list[str] | None
    matched_codes: list[CodeMatch]
    chunks: list[RetrievedChunk]
    expanded_query: str | None = None  # LLM rewrite used for search when no code was typed

    @property
    def top_score(self) -> float:
        return max((c.score for c in self.chunks), default=0.0)


def passage_text(chunk: StoredChunk) -> str:
    return f"{chunk.heading_path}\n{chunk.text}"


class HybridRetriever:
    """Code queries: the exact fault entry is pinned first, then keyword + vector results reranked.

    Symptom queries (no code typed) add two things measured on the eval's symptom scenarios
    (hit@5 8/18 -> 18/18): an LLM rewrite into manual vocabulary that drives extra searches and the
    reranker, and a fault-only vector search whose best `fault_slots` entries are kept right after
    the reranker's top `slot_position` results, because the reranker favours settings pages over
    the fault entry the operator actually needs.
    """

    def __init__(self, backend: SearchBackend, embedder: Embedder, reranker: Reranker,
                 candidates: int = 30, top_k: int = 8, rewriter: Rewriter | None = None,
                 fault_candidates: int = 10, fault_slots: int = 2, slot_position: int = 2):
        self._backend = backend
        self._embedder = embedder
        self._reranker = reranker
        self._candidates = candidates
        self._top_k = top_k
        self._rewriter = rewriter
        self._fault_candidates = fault_candidates
        self._fault_slots = fault_slots
        self._slot_position = slot_position
        self._fault_index: dict[str, list[FaultHit]] | None = None

    def fault_index(self) -> dict[str, list[FaultHit]]:
        if self._fault_index is None:
            self._fault_index = self._backend.fault_index()
        return self._fault_index

    def detect_codes(self, query: str, manual_ids: list[str] | None = None) -> list[CodeMatch]:
        """Exact matches first; display look-alikes only for manuals without an exact match."""
        index = self.fault_index()

        def allowed(hit: FaultHit) -> bool:
            return manual_ids is None or hit.manual_id in manual_ids

        matches: list[CodeMatch] = []
        seen: set[str] = set()
        for token in query_code_candidates(query):
            key = code_key(token)
            exact = [h for h in index.get(key, []) if allowed(h)]
            covered = {h.manual_id for h in exact}
            # Look-alikes only for tokens that read like a display (a digit, or all capitals):
            # otherwise the word "info" would become INF0 through O/0.
            reads_like_display = any(ch.isdigit() for ch in token) or token.isupper()
            lookalike = [
                h for variant in sorted(confusable_variants(key)) for h in index.get(variant, [])
                if allowed(h) and h.manual_id not in covered
            ] if reads_like_display else []
            for hit, fuzzy in [(h, False) for h in exact] + [(h, True) for h in lookalike]:
                if hit.chunk_id not in seen:
                    seen.add(hit.chunk_id)
                    matches.append(CodeMatch(hit, token, fuzzy))
        return matches

    def retrieve(self, query: str, manual_ids: list[str] | None = None) -> RetrievalResult:
        codes = self.detect_codes(query, manual_ids)
        expanded = self._rewriter.rewrite(query) if (self._rewriter and not codes) else None
        search_text = expanded or query
        texts = [query] + ([expanded] if expanded else [])
        vectors = dict(zip(texts, self._embedder.embed(texts)))
        rankings: list[list[str]] = []
        for text in texts:
            rankings.append([cid for cid, _ in self._backend.keyword_search(text, manual_ids, self._candidates)])
            rankings.append([cid for cid, _ in self._backend.vector_search(vectors[text], manual_ids, self._candidates)])
        reserved: list[str] = []
        if not codes:
            lane = [cid for cid, _ in self._backend.vector_search(
                vectors[search_text], manual_ids, self._fault_candidates, kind="fault")]
            rankings.append(lane)
            reserved = lane[: self._fault_slots]
        exact_ids = [m.hit.chunk_id for m in codes]
        fused = [cid for cid, _ in rrf(rankings) if cid not in exact_ids][: self._candidates]
        fused += [cid for cid in reserved if cid not in fused]
        stored = self._backend.get_chunks(exact_ids + fused)
        pool = [stored[cid] for cid in fused if cid in stored]
        scores = self._reranker.score(search_text, [passage_text(c) for c in pool]) if pool else []
        scored = {c.id: float(s) for c, s in zip(pool, scores)}
        ranked = [RetrievedChunk(c, scored[c.id]) for c in sorted(pool, key=lambda c: -scored[c.id])]
        kept = [r for r in ranked if r.chunk.id in reserved]
        kept.sort(key=lambda r: reserved.index(r.chunk.id))
        rest = [r for r in ranked if r.chunk.id not in reserved]
        ordered = rest[: self._slot_position] + kept + rest[self._slot_position:]
        pinned = [RetrievedChunk(stored[m.hit.chunk_id], 1.0, m.hit.code) for m in codes if m.hit.chunk_id in stored]
        keep = max(self._top_k, len(pinned))
        return RetrievalResult(query, manual_ids, codes, (pinned + ordered)[:keep], expanded)
