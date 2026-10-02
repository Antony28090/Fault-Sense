import pytest

from faultsense.eval.drafting import draft_scenarios

FAULTS = {
    "atv600": {"OHF": {"code": "OHF", "code_key": "OHF", "causes": ["a", "b", "c", "d", "e"], "page": 672, "page_end": 672}},
    "atv900": {"OHF": {"code": "OHF", "code_key": "OHF", "causes": ["x"], "page": 680, "page_end": 681}},
    "atv12": {"INFI": {"code": "InFI", "code_key": "INFI", "causes": ["Power card differs"], "page": 111, "page_end": 111}},
}


def test_targets_supply_codes_causes_and_pages():
    [s] = draft_scenarios([{"id": "s1", "type": "fault_code", "query": "OHF on pump", "machine_id": "DEMO-PUMP-01",
                            "targets": [{"manual": "atv600", "code": "OHF"}]}], FAULTS)
    assert s["expected_fault_codes"] == ["OHF"]
    assert s["expected_causes"] == ["a", "b", "c", "d"]
    assert s["expected_sources"] == [{"manual": "atv600", "pages": [672]}]
    assert s["reviewed"] is False and s["expected_behavior"] == "diagnose"
    assert s["notes"] == "Drafted from atv600 OHF p.672"


def test_target_without_manual_expands_to_every_manual_with_the_code():
    [s] = draft_scenarios([{"id": "s2", "type": "fault_code", "query": "What is OHF?", "targets": [{"code": "OHF"}]}], FAULTS)
    assert s["expected_sources"] == [{"manual": "atv600", "pages": [672]}, {"manual": "atv900", "pages": [680, 681]}]


def test_lookalike_target_finds_the_printed_code():
    [s] = draft_scenarios([{"id": "s3", "type": "fault_code", "query": "InF1", "targets": [{"manual": "atv12", "code": "InF1"}]}], FAULTS)
    assert s["expected_fault_codes"] == ["InFI"]


def test_out_of_scope_and_hand_written_expectations():
    oos, hand = draft_scenarios([
        {"id": "o", "type": "out_of_scope", "query": "weather?"},
        {"id": "h", "type": "symptom", "query": "blank display", "expected_causes": ["No supply"],
         "expected_sources": [{"manual": "atv12", "pages": [111]}]},
    ], FAULTS)
    assert oos["expected_behavior"] == "escalate" and oos["expected_sources"] == [] and oos["expected_causes"] == []
    assert hand["expected_causes"] == ["No supply"]
    assert hand["expected_sources"] == [{"manual": "atv12", "pages": [111]}]


def test_unknown_code_for_a_named_manual_is_an_error():
    with pytest.raises(ValueError, match="not found"):
        draft_scenarios([{"id": "x", "type": "fault_code", "query": "q",
                          "targets": [{"manual": "atv600", "code": "ZZZ9"}]}], FAULTS)
