from datetime import datetime, timezone

import pytest

from helpers import SPECS
from faultsense.db.repository import FaultHit, StoredChunk
from faultsense.diagnosis.service import DiagnosisService, UnknownMachine
from faultsense.llm.base import LLMError, LLMRefusal
from faultsense.llm.fake import FakeLLM
from faultsense.manifest import MachineSpec
from faultsense.retrieval.retriever import CodeMatch, RetrievalResult, RetrievedChunk
from faultsense.telemetry import Reading

MANUALS = {"atv600": SPECS["atv600"]}
MACHINES = {"DEMO-PUMP-01": MachineSpec(id="DEMO-PUMP-01", manual="atv600")}
FAULT = StoredChunk("atv600:f:OHF", "atv600", "fault", "Error codes > OHF [Device Overheat]", 672, 672,
                    "Fault code OHF: Device Overheat\nProbable causes:\n- Ambient temperature too high.")
SAFETY = StoredChunk("atv600:s00010", "atv600", "safety", "About The Document", 12, 12,
                     "DANGER Disconnect all power. Wait 15 minutes. Measure the DC bus voltage.")
GOOD = {
    "status": "diagnosis", "insufficient_reason": "",
    "probable_causes": [{"cause": "Ambient temperature too high.", "confidence": 0.9, "fault_code": "OHF", "source_ids": ["S1"]}],
    "corrective_actions": [{"action": "Clean the heat sink.", "requires_isolation": True, "source_ids": ["S1"]}],
    "safety_warnings": [{"text": "Disconnect all power and wait for the DC bus to discharge.", "source_ids": ["S2"]}],
}
BAD_CITATION = GOOD | {"probable_causes": [GOOD["probable_causes"][0] | {"source_ids": ["S99"]}]}


def result(with_code=True, score=1.0):
    matches = [CodeMatch(FaultHit("atv600", "OHF", "Device Overheat", FAULT.id, 672), "OHF", False)] if with_code else []
    return RetrievalResult("q", ["atv600"], matches, [RetrievedChunk(FAULT, score, "OHF" if with_code else None)])


class FakeRetriever:
    def __init__(self, res):
        self.res = res
        self.calls = []

    def retrieve(self, query, manual_ids=None):
        self.calls.append((query, manual_ids))
        return self.res


class FakeRepo:
    def safety_chunks(self, manual_ids):
        return [SAFETY] if "atv600" in manual_ids else []

    def get_chunks(self, ids):
        return {c.id: c for c in (FAULT, SAFETY) if c.id in ids}

    def known_identifiers_by_manual(self):
        return {"atv600": ({"OHF", "CLI"}, {"current limitation"}), "atv320": ({"BLC"}, {"brake logic control"})}


class StubTelemetry:
    def recent(self, machine_id, window):
        return [Reading(datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc), "motor_current", 12.5, "A")]


def make_service(llm, res=None, telemetry=None, retriever=None):
    return DiagnosisService(retriever or FakeRetriever(res or result()), FakeRepo(), llm, MANUALS, MACHINES,
                            telemetry=telemetry, evidence_threshold=0.30)


def test_grounded_answer_resolves_citations_to_manual_pages():
    llm = FakeLLM([GOOD])
    response = make_service(llm).diagnose("Pump shows OHF", "DEMO-PUMP-01")
    assert response.status == "diagnosis"
    assert response.probable_causes[0].citations[0].model_dump() == {
        "source_id": "S1", "manual": "atv600", "manual_title": "Altivar Process ATV600 Programming Manual", "page": 672,
    }
    assert response.corrective_actions[0].requires_isolation is True
    assert response.safety_warnings[0].citations[0].page == 12
    assert [(s.id, s.kind) for s in response.sources] == [("S1", "fault"), ("S2", "safety")]
    assert response.matched_fault_codes[0].code == "OHF"
    assert response.meta.llm_called and response.meta.guard_retries == 0
    assert 'id="S2"' in llm.calls[0]["user"]


def test_weak_evidence_escalates_without_calling_the_llm():
    llm = FakeLLM([])
    response = make_service(llm, result(with_code=False, score=0.1)).diagnose("Hydraulic press leaking", None)
    assert response.status == "escalate" and llm.calls == []
    assert "evidence threshold" in response.escalation.reason
    assert response.escalation.collect
    assert [s.id for s in response.escalation.sources_considered] == ["S1"]
    assert response.probable_causes == [] and response.meta.llm_called is False


def test_unknown_citation_triggers_one_retry_then_succeeds():
    llm = FakeLLM([BAD_CITATION, GOOD])
    response = make_service(llm).diagnose("Pump shows OHF", "DEMO-PUMP-01")
    assert response.status == "diagnosis" and response.meta.guard_retries == 1
    assert "cause 1: unknown source id S99" in response.meta.first_pass_violations
    assert "REJECTED" in llm.calls[1]["user"]


def test_two_failed_attempts_escalate():
    response = make_service(FakeLLM([BAD_CITATION, BAD_CITATION])).diagnose("Pump shows OHF", "DEMO-PUMP-01")
    assert response.status == "escalate" and "grounding checks" in response.escalation.reason
    assert response.meta.final_violations


def test_schema_violation_triggers_retry():
    response = make_service(FakeLLM([{"status": "diagnosis"}, GOOD])).diagnose("Pump shows OHF", "DEMO-PUMP-01")
    assert response.status == "diagnosis"
    assert response.meta.first_pass_violations[0].startswith("schema:")


@pytest.mark.parametrize("error", [LLMRefusal("declined"), LLMError("connection refused")])
def test_llm_error_escalates(error):
    response = make_service(FakeLLM([error])).diagnose("Pump shows OHF", "DEMO-PUMP-01")
    assert response.status == "escalate"
    assert "could not produce an answer" in response.escalation.reason


def test_insufficient_evidence_shows_a_fixed_reason_and_keeps_the_llm_note_for_engineers():
    answer = {"status": "insufficient_evidence", "insufficient_reason": "Measure the DC bus terminals to check.",
              "probable_causes": [], "corrective_actions": [], "safety_warnings": []}
    response = make_service(FakeLLM([answer])).diagnose("Pump shows OHF", "DEMO-PUMP-01")
    assert response.status == "escalate"
    assert "DC bus" not in response.escalation.reason and "DC bus" not in response.escalation.summary
    assert response.escalation.reason.startswith("The retrieved manual passages do not cover this problem")
    assert response.meta.llm_note == "Measure the DC bus terminals to check."


def test_unknown_machine_raises():
    with pytest.raises(UnknownMachine):
        make_service(FakeLLM([])).diagnose("OHF", "NOPE")


def test_machine_restricts_retrieval():
    retriever = FakeRetriever(result())
    make_service(FakeLLM([GOOD]), retriever=retriever).diagnose("OHF", "DEMO-PUMP-01")
    assert retriever.calls == [("OHF", ["atv600"])]


def test_confidence_is_capped_by_retrieval_strength_without_a_code():
    response = make_service(FakeLLM([GOOD]), result(with_code=False, score=0.6)).diagnose("pump hot", "DEMO-PUMP-01")
    assert response.probable_causes[0].confidence == 0.6


def test_telemetry_readings_reach_the_prompt():
    llm = FakeLLM([GOOD])
    make_service(llm, telemetry=StubTelemetry()).diagnose("Pump shows OHF", "DEMO-PUMP-01")
    assert "<telemetry>" in llm.calls[0]["user"] and "motor_current=12.5 A" in llm.calls[0]["user"]


def test_lookalike_code_match_is_explained_to_the_llm():
    match = CodeMatch(FaultHit("atv600", "OHF", "Device Overheat", FAULT.id, 672), "0HF", True)
    res = RetrievalResult("q", ["atv600"], [match], [RetrievedChunk(FAULT, 1.0, "OHF")])
    llm = FakeLLM([GOOD])
    make_service(llm, res).diagnose("Pump shows 0HF", "DEMO-PUMP-01")
    assert "OHF (atv600 p.672): the operator typed '0HF', which looks the same" in llm.calls[0]["user"]


def test_identifiers_from_another_manual_are_rejected_for_this_machine():
    other_manual = GOOD | {"corrective_actions": [{"action": "Check [Brake logic control] BLC.", "requires_isolation": False, "source_ids": ["S1"]}]}
    llm = FakeLLM([other_manual, GOOD])
    response = make_service(llm).diagnose("Pump shows OHF", "DEMO-PUMP-01")
    assert response.meta.guard_retries == 1
    assert "step 1: unknown identifier [Brake logic control]" in response.meta.first_pass_violations
    assert "step 1: unknown identifier BLC" in response.meta.first_pass_violations


def test_known_identifiers_can_be_limited_to_manuals():
    service = make_service(FakeLLM([]))
    assert service.known_identifiers(["atv600"]).knows_code("OHF")
    assert not service.known_identifiers(["atv600"]).knows_code("BLC")
    assert service.known_identifiers().knows_code("BLC")


def test_response_records_what_retrieval_found_for_evaluation():
    res = result(with_code=False, score=0.62)
    res.expanded_query = "device overheating at high ambient temperature"
    response = make_service(FakeLLM([GOOD]), res).diagnose("Pump trips on hot afternoons", "DEMO-PUMP-01")
    assert [(s.id, s.score) for s in response.sources] == [("S1", 0.62), ("S2", None)]  # S2: safety added by the service
    assert response.meta.search_query == "device overheating at high ambient temperature"
    escalated = make_service(FakeLLM([]), result(with_code=False, score=0.05)).diagnose("weather?", None)
    assert [(s.id, s.score) for s in escalated.sources] == [("S1", 0.05), ("S2", None)]


def all_manuals_service(llm, res=None, retriever=None):
    machines = {"DEMO-PUMP-01": MachineSpec(id="DEMO-PUMP-01", manual="atv600")}
    return DiagnosisService(retriever or FakeRetriever(res or result()), FakeRepo(), llm, dict(SPECS), machines,
                            evidence_threshold=0.30)


def test_a_drive_without_a_manual_escalates_without_searching():
    retriever, llm = FakeRetriever(result()), FakeLLM([])
    response = all_manuals_service(llm, retriever=retriever).diagnose("When does an ATV61 trip on OHF?")
    assert response.status == "escalate" and retriever.calls == [] and llm.calls == []
    assert "ATV61" in response.escalation.reason and "ATV320" in response.escalation.reason
    assert response.meta.named_models == ["ATV61"]


def test_a_named_drive_model_limits_the_search_to_its_manual():
    retriever = FakeRetriever(result())
    all_manuals_service(FakeLLM([GOOD]), retriever=retriever).diagnose("ATV630 shows OHF")
    assert retriever.calls == [("ATV630 shows OHF", ["atv600"])]


def test_the_named_model_wins_over_a_stale_machine_choice():
    retriever = FakeRetriever(result())
    # The fake retriever returns ATV600 chunks whatever it is asked, so the answer itself is not checked here.
    all_manuals_service(FakeLLM([GOOD, GOOD]), retriever=retriever).diagnose("ATV320 shows OHF", "DEMO-PUMP-01")
    assert retriever.calls == [("ATV320 shows OHF", ["atv320"])]


def test_a_replaced_old_drive_does_not_block_the_answer_for_the_new_one():
    retriever = FakeRetriever(result())
    response = all_manuals_service(FakeLLM([GOOD]), retriever=retriever).diagnose(
        "We replaced the ATV61 with an ATV630 and now it shows OHF")
    assert retriever.calls[0][1] == ["atv600"] and response.status == "diagnosis"


def test_progress_reports_each_stage_with_what_was_found():
    stages = []
    make_service(FakeLLM([GOOD])).diagnose("Pump shows OHF", "DEMO-PUMP-01",
                                           progress=lambda stage, detail: stages.append((stage, detail)))
    assert [s for s, _ in stages] == ["search", "found", "write"]
    found = stages[1][1]
    assert found["codes"] == ["OHF"] and found["pages"] == 1
    assert found["top"] == {"manual": "atv600", "family": "ATV600", "page": 672, "heading": FAULT.heading_path}


def test_progress_reports_a_rejected_draft():
    stages = []
    make_service(FakeLLM([BAD_CITATION, GOOD])).diagnose("Pump shows OHF", "DEMO-PUMP-01",
                                                         progress=lambda stage, detail: stages.append(stage))
    assert stages == ["search", "found", "write", "retry"]


def test_passage_returns_the_manual_text_behind_a_citation():
    service = make_service(FakeLLM([]))
    passage = service.passage(FAULT.id)
    assert passage["text"] == FAULT.text and passage["family"] == "ATV600"
    assert (passage["page_start"], passage["heading"]) == (672, FAULT.heading_path)
    assert service.passage("atv600:nope") is None
