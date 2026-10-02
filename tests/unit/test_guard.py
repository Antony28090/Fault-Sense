from faultsense.diagnosis.guard import KnownIdentifiers, check_llm_output, unknown_identifiers
from faultsense.diagnosis.schema import LLMDiagnosis

KNOWN = KnownIdentifiers(frozenset({"OHF", "CLI", "SFR", "INFI", "KHZ"}), frozenset({"current limitation"}))
VALID, SAFETY = {"S1", "S2"}, {"S2"}


def _answer(**overrides):
    base = {
        "status": "diagnosis", "insufficient_reason": "",
        "probable_causes": [{"cause": "Ambient temperature too high.", "confidence": 0.8, "fault_code": "OHF", "source_ids": ["S1"]}],
        "corrective_actions": [{"action": "Clean the heat sink.", "requires_isolation": True, "source_ids": ["S1"]}],
        "safety_warnings": [{"text": "Disconnect all power and wait 15 minutes.", "source_ids": ["S2"]}],
    }
    return LLMDiagnosis.model_validate(base | overrides)


def test_known_codes_match_case_and_display_lookalikes():
    assert KNOWN.knows_code("ohf") and KNOWN.knows_code("0HF") and KNOWN.knows_code("InF1")
    assert not KNOWN.knows_code("OHF9")


def test_unknown_identifiers_flags_invented_codes_and_labels():
    text = "Reduce [Current Limitation] CLI, check [Motor Current Limit] and fault OHF9. Measure the DC bus (S1)."
    assert unknown_identifiers(text, KNOWN) == ["[Motor Current Limit]", "OHF9"]


def test_grounded_answer_passes():
    assert check_llm_output(_answer(), VALID, SAFETY, KNOWN) == []


def test_missing_and_unknown_citations_are_violations():
    out = _answer(corrective_actions=[
        {"action": "Clean the heat sink.", "requires_isolation": False, "source_ids": []},
        {"action": "Verify the fans.", "requires_isolation": False, "source_ids": ["S99"]},
    ])
    assert check_llm_output(out, VALID, SAFETY, KNOWN) == ["step 1: no citation", "step 2: unknown source id S99"]


def test_isolation_needs_a_warning_citing_a_safety_source():
    out = _answer(safety_warnings=[{"text": "Be careful.", "source_ids": ["S1"]}])
    assert check_llm_output(out, VALID, SAFETY, KNOWN) == [
        "steps require isolation but no safety warning cites a safety source",
    ]


def test_invented_fault_code_is_a_violation():
    out = _answer(probable_causes=[{"cause": "Fan failure.", "confidence": 0.5, "fault_code": "xyzf", "source_ids": ["S1"]}])
    assert check_llm_output(out, VALID, SAFETY, KNOWN) == ["cause 1: unknown identifier xyzf"]


def test_insufficient_evidence_is_not_checked():
    out = _answer(status="insufficient_evidence", probable_causes=[], corrective_actions=[], safety_warnings=[])
    assert check_llm_output(out, VALID, SAFETY, KNOWN) == []
