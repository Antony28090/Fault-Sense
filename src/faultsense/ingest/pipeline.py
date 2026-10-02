"""Embed one extracted manual and store it; manuals whose PDF is unchanged are skipped."""
from __future__ import annotations

from faultsense.embeddings import Embedder
from faultsense.ingest.extract import ExtractedManual
from faultsense.ingest.sectioner import Chunk


def embedding_text(family: str, chunk: Chunk) -> str:
    return f"{family} | {chunk.heading_path}\n{chunk.text}"


def ingest_manual(ex: ExtractedManual, repo, embedder: Embedder, force: bool = False) -> str:
    if not force and repo.manual_hashes().get(ex.spec.id) == ex.sha256:
        return "unchanged"
    vectors = embedder.embed([embedding_text(ex.spec.family, chunk) for chunk in ex.chunks])
    repo.replace_manual(ex, vectors)
    return "ingested"
