"""Builds the real object graph (database, models) from Settings. Tests use fakes instead."""
from __future__ import annotations

from dataclasses import dataclass

from faultsense.config import Settings, get_settings
from faultsense.db.connection import connect
from faultsense.db.repository import Repository
from faultsense.embeddings import BgeM3Embedder, Embedder
from faultsense.manifest import MachineSpec, ManualSpec, load_machines, load_manuals
from faultsense.retrieval.rerank import BgeReranker
from faultsense.retrieval.retriever import HybridRetriever
from faultsense.retrieval.rewrite import QueryRewriter


@dataclass
class Components:
    settings: Settings
    manuals: dict[str, ManualSpec]
    machines: dict[str, MachineSpec]
    repo: Repository
    embedder: Embedder
    retriever: HybridRetriever


def build_rewriter(settings: Settings) -> QueryRewriter | None:
    """Query rewriting is a short, cheap call: low effort, and optionally its own provider and model."""
    if not settings.query_rewrite:
        return None
    from faultsense.llm import get_provider

    rewrite = settings.model_copy(update={"llm_effort": settings.rewrite_effort,
                                          "llm_provider": settings.effective_rewrite_provider,
                                          "llm_model": settings.effective_rewrite_model})
    return QueryRewriter(get_provider(rewrite))


def build_catalog(settings: Settings | None = None):
    """Machines, manual PDF paths and model names for the operator page; reads only the YAML manifests."""
    from faultsense.api import Catalog

    s = settings or get_settings()
    manuals = {spec.id: spec for spec in load_manuals(s.data_dir / "manuals.yaml")}
    machines = load_machines(s.data_dir / "machines.yaml", list(manuals.values()))
    return Catalog(
        machines=[{"id": m.id, "manual": m.manual, "family": manuals[m.manual].family, "description": m.description}
                  for m in machines.values()],
        manual_files={manual_id: s.manuals_dir / spec.file for manual_id, spec in manuals.items()},
        engine={"diagnosis": f"{s.llm_provider} {s.llm_model}",
                "rewrite": f"{s.effective_rewrite_provider} {s.effective_rewrite_model}" if s.query_rewrite else None},
    )


def build_translator(settings: Settings | None = None):
    s = settings or get_settings()
    if s.translation == "off":
        return None
    if s.translation != "indictrans2":
        raise ValueError(f"Unknown TRANSLATION {s.translation!r}: use indictrans2 or off")
    from faultsense.translation import IndicTrans2Translator

    return IndicTrans2Translator(python=s.translation_python_path, token=s.hf_token or None,
                                 device=s.translation_device, idle_minutes=s.translation_idle_minutes,
                                 beams=s.translation_beams)


def build_language_layer(settings: Settings | None = None):
    from faultsense.language import IdentityLanguageLayer, IndicLanguageLayer

    translator = build_translator(settings)
    return IndicLanguageLayer(translator) if translator else IdentityLanguageLayer()


def build_components(settings: Settings | None = None) -> Components:
    s = settings or get_settings()
    manuals = {spec.id: spec for spec in load_manuals(s.data_dir / "manuals.yaml")}
    machines = load_machines(s.data_dir / "machines.yaml", list(manuals.values()))
    repo = Repository(connect(s.database_url, s.db_schema), reconnect=lambda: connect(s.database_url, s.db_schema))
    embedder = BgeM3Embedder(s.embedding_model, s.device)
    retriever = HybridRetriever(repo, embedder, BgeReranker(s.reranker_model, s.device),
                                rewriter=build_rewriter(s))
    return Components(s, manuals, machines, repo, embedder, retriever)


def build_service(components: Components | None = None):
    from faultsense.diagnosis.service import DiagnosisService
    from faultsense.llm import get_provider

    c = components or build_components()
    return DiagnosisService(c.retriever, c.repo, get_provider(c.settings), c.manuals, c.machines,
                            language=build_language_layer(c.settings),
                            evidence_threshold=c.settings.evidence_threshold)
