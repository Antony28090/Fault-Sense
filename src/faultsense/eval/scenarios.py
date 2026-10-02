"""Eval scenario file (data/eval/scenarios.yaml)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class ExpectedSource(BaseModel):
    manual: str
    pages: list[int]


class Scenario(BaseModel):
    id: str
    type: Literal["fault_code", "symptom", "out_of_scope"]
    query: str
    machine_id: str | None = None
    expected_behavior: Literal["diagnose", "escalate"]
    expected_fault_codes: list[str] = []
    expected_causes: list[str] = []
    expected_sources: list[ExpectedSource] = []
    reviewed: bool = False
    notes: str = ""
    source_url: str = ""  # where a real-world scenario came from (e.g. a Schneider Electric FAQ)
    reference_answer: str = ""  # that source's answer, paraphrased, for reviewers to compare against


def load_scenarios(path: Path) -> list[Scenario]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    scenarios = [Scenario(**raw) for raw in data]
    ids = [s.id for s in scenarios]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate scenario ids: {duplicates}")
    return scenarios
