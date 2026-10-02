from datetime import timedelta

from faultsense.diagnosis.schema import DiagnosisResponse, Meta
from faultsense.language import IdentityLanguageLayer
from faultsense.telemetry import NullTelemetrySource


def _response():
    return DiagnosisResponse(
        status="escalate", query="q", machine_id=None, language="en", matched_fault_codes=[],
        probable_causes=[], corrective_actions=[], safety_warnings=[], escalation=None, sources=[],
        meta=Meta(retrieval_top_score=0.0),
    )


def test_null_telemetry_returns_nothing():
    assert NullTelemetrySource().recent("DEMO-PUMP-01", timedelta(minutes=30)) == []


def test_identity_language_layer_passes_text_and_answers_through():
    layer = IdentityLanguageLayer()
    assert layer.to_english("OHF on pump") == ("OHF on pump", "en")
    response = _response()
    assert layer.from_english(response, "en") is response
