import pytest

from faultsense.config import PROJECT_ROOT
from faultsense.manifest import load_machines, load_manuals

DATA = PROJECT_ROOT / "data"


def test_real_manifest_lists_four_manuals():
    specs = load_manuals(DATA / "manuals.yaml")
    assert [s.id for s in specs] == ["atv12", "atv320", "atv600", "atv900"]
    atv600 = specs[2]
    assert atv600.fault_layout == "block"
    assert atv600.fault_pages == (645, 687)
    assert atv600.index_pages == (641, 643)
    assert specs[0].index_pages is None
    assert atv600.path(DATA / "manuals").name == "ATV600-Programming-Manual-EN-EAV64318-14.pdf"


def test_real_machines_refer_to_known_manuals():
    specs = load_manuals(DATA / "manuals.yaml")
    machines = load_machines(DATA / "machines.yaml", specs)
    assert machines["DEMO-PUMP-01"].manual == "atv600"
    assert len(machines) == 4


def test_machine_with_unknown_manual_is_rejected(tmp_path):
    specs = load_manuals(DATA / "manuals.yaml")
    bad = tmp_path / "machines.yaml"
    bad.write_text("machines:\n  - {id: M1, manual: atv999}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown manual"):
        load_machines(bad, specs)


def test_each_manual_lists_the_drive_models_it_covers():
    specs = {spec.id: spec for spec in load_manuals(PROJECT_ROOT / "data" / "manuals.yaml")}
    assert specs["atv12"].models == ["ATV12"]
    assert specs["atv320"].models == ["ATV320"]
    assert {"ATV630", "ATV650", "ATV6B0"} <= set(specs["atv600"].models)
    assert {"ATV930", "ATV980", "ATV9A0"} <= set(specs["atv900"].models)
