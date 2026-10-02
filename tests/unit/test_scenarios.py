from collections import Counter

import pytest

from helpers import DATA_DIR, SPECS
from faultsense.eval.scenarios import load_scenarios
from faultsense.manifest import load_machines


def test_duplicate_ids_are_rejected(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        "- {id: a, type: out_of_scope, query: q, expected_behavior: escalate}\n"
        "- {id: a, type: out_of_scope, query: r, expected_behavior: escalate}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_scenarios(path)


def test_committed_scenarios_file_shape():
    scenarios = load_scenarios(DATA_DIR / "eval" / "scenarios.yaml")
    machines = load_machines(DATA_DIR / "machines.yaml", list(SPECS.values()))
    assert len(scenarios) == 40
    assert Counter(s.type for s in scenarios) == {"fault_code": 18, "symptom": 18, "out_of_scope": 4}
    assert all(s.reviewed is False for s in scenarios)
    assert all(s.machine_id is None or s.machine_id in machines for s in scenarios)
    for s in scenarios:
        if s.type == "out_of_scope":
            assert s.expected_behavior == "escalate" and not s.expected_sources and not s.expected_causes
        else:
            assert s.expected_behavior == "diagnose" and s.expected_sources and s.expected_causes
            assert all(src.manual in SPECS for src in s.expected_sources)


def test_web_scenarios_keep_their_source_and_reference_answer(tmp_path):
    path = tmp_path / "web.yaml"
    path.write_text(
        "- id: web-atv320-ohf\n"
        "  type: fault_code\n"
        "  query: Conveyor drive trips on OHF\n"
        "  expected_behavior: diagnose\n"
        "  source_url: https://www.se.com/us/en/faqs/FA377302/\n"
        "  reference_answer: Drive too hot; check load, ventilation, ambient and fans.\n",
        encoding="utf-8",
    )
    [scenario] = load_scenarios(path)
    assert scenario.source_url == "https://www.se.com/us/en/faqs/FA377302/"
    assert scenario.reference_answer.startswith("Drive too hot")


def test_committed_web_scenarios_file_shape():
    scenarios = load_scenarios(DATA_DIR / "eval" / "scenarios_web.yaml")
    machines = load_machines(DATA_DIR / "machines.yaml", list(SPECS.values()))
    assert len(scenarios) >= 50
    assert all(s.id.startswith("web-") and s.reviewed is False for s in scenarios)
    assert all(s.source_url.startswith("https://") and "se.com" in s.source_url for s in scenarios)
    assert all(s.reference_answer.strip() for s in scenarios)
    assert len({s.query.lower() for s in scenarios}) == len(scenarios)
    assert all(s.machine_id is None or s.machine_id in machines for s in scenarios)
    for s in scenarios:
        if s.type == "out_of_scope":
            assert s.expected_behavior == "escalate" and not s.expected_sources and not s.expected_causes
        else:
            assert s.expected_behavior == "diagnose" and s.expected_sources and s.expected_causes
            assert all(src.manual in SPECS for src in s.expected_sources)
        if s.type == "fault_code":
            assert s.expected_fault_codes
