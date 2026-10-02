from faultsense.diagnosis.schema import (
    LLM_OUTPUT_SCHEMA, Cause, Citation, DiagnosisResponse, LLMDiagnosis, Meta, SourceRef,
)


def _objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for value in node.values():
            yield from _objects(value)
    elif isinstance(node, list):
        for value in node:
            yield from _objects(value)


def test_llm_schema_is_strict_for_structured_outputs():
    objects = list(_objects(LLM_OUTPUT_SCHEMA))
    assert len(objects) == 4
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert sorted(obj["required"]) == sorted(obj["properties"])


def test_llm_model_accepts_a_schema_shaped_answer():
    raw = {
        "status": "diagnosis", "insufficient_reason": "",
        "probable_causes": [{"cause": "Ambient temperature too high.", "confidence": 0.8, "fault_code": "OHF", "source_ids": ["S1"]}],
        "corrective_actions": [{"action": "Clean the heat sink.", "requires_isolation": True, "source_ids": ["S1"]}],
        "safety_warnings": [{"text": "Disconnect all power.", "source_ids": ["S2"]}],
    }
    assert LLMDiagnosis.model_validate(raw).probable_causes[0].fault_code == "OHF"


def test_response_round_trips_through_json():
    citation = Citation(source_id="S1", manual="atv600", manual_title="ATV600 manual", page=672)
    response = DiagnosisResponse(
        status="diagnosis", query="OHF", machine_id="DEMO-PUMP-01", language="en", matched_fault_codes=[],
        probable_causes=[Cause(rank=1, cause="Ambient temperature too high.", confidence=0.8, fault_code="OHF", citations=[citation])],
        corrective_actions=[], safety_warnings=[], escalation=None,
        sources=[SourceRef(id="S1", chunk_id="atv600:f:OHF", manual="atv600", manual_title="ATV600 manual",
                           family="ATV600", page_start=672, page_end=672, heading="Error codes > OHF", kind="fault")],
        meta=Meta(retrieval_top_score=1.0, llm_called=True),
    )
    assert DiagnosisResponse.model_validate_json(response.model_dump_json()) == response
