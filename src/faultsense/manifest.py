"""Manual manifest (data/manuals.yaml) and machine registry (data/machines.yaml)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class ManualSpec(BaseModel):
    id: str
    family: str
    title: str
    doc_ref: str
    version: str
    file: str
    url: str
    sha256: str
    fault_layout: Literal["block", "table4"]
    fault_pages: tuple[int, int]
    index_pages: tuple[int, int] | None = None
    safety_pages: list[int]
    models: list[str] = []  # drive models this manual covers (taken from the manual's own text)

    def path(self, manuals_dir: Path) -> Path:
        return Path(manuals_dir) / self.file


class MachineSpec(BaseModel):
    id: str
    manual: str
    description: str = ""


def load_manuals(path: Path) -> list[ManualSpec]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    specs = [ManualSpec(**raw) for raw in data["manuals"]]
    ids = [spec.id for spec in specs]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate manual ids in {path}")
    return specs


def load_machines(path: Path, manuals: list[ManualSpec]) -> dict[str, MachineSpec]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    known = {spec.id for spec in manuals}
    machines: dict[str, MachineSpec] = {}
    for raw in data.get("machines", []):
        machine = MachineSpec(**raw)
        if machine.manual not in known:
            raise ValueError(f"machine {machine.id} refers to unknown manual {machine.manual!r}")
        if machine.id in machines:
            raise ValueError(f"duplicate machine id {machine.id}")
        machines[machine.id] = machine
    return machines
