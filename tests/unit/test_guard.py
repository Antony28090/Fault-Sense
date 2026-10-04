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


def test_a_fault_code_written_with_its_bracketed_name_is_checked_as_code_and_name():
    known = KnownIdentifiers(frozenset({"TNF"}), frozenset({"autotuning error"}))
    cause = {"cause": "Autotuning did not finish.", "confidence": 0.6, "source_ids": ["S1"]}
    ok = _answer(probable_causes=[cause | {"fault_code": "[Autotuning Error] TNF"}])
    assert check_llm_output(ok, VALID, SAFETY, known) == []
    bad = _answer(probable_causes=[cause | {"fault_code": "[Tuning Fault] TNF9"}])
    assert check_llm_output(bad, VALID, SAFETY, known) == [
        "cause 1: unknown identifier [Tuning Fault]", "cause 1: unknown identifier TNF9"]


def test_labels_match_whether_words_are_joined_by_underscores_or_spaces():
    known = KnownIdentifiers(frozenset(), frozenset({"brh_b4_freq", "motor th current"}))
    assert known.knows_label("BRH b4_freq") and known.knows_label("BRH_b4_freq") and known.knows_label("Motor_Th_Current")
    assert not known.knows_label("BRH b5 freq")


def test_a_repeated_cause_is_a_violation():
    cause = {"cause": "Ambient temperature too high.", "confidence": 0.8, "fault_code": "OHF", "source_ids": ["S1"]}
    out = _answer(probable_causes=[cause, cause | {"cause": " ambient  temperature too high"}, cause | {"cause": "Blocked air inlet."}])
    assert check_llm_output(out, VALID, SAFETY, KNOWN) == ["cause 2 repeats cause 1: list each cause once"]


def test_plurals_of_generic_terms_are_not_identifiers():
    assert unknown_identifiers("Check the IDs of both PLCs and the LEDs on the IGBTs.", KNOWN) == []
    assert unknown_identifiers("Check OHFs.", KNOWN) == []  # a known code in the plural
    assert unknown_identifiers("Check XQZs.", KNOWN) == ["XQZs"]
