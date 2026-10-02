from datetime import datetime, timezone

from faultsense.diagnosis.prompt import SYSTEM_PROMPT, PromptSource, build_user_prompt
from faultsense.telemetry import Reading

SOURCES = [
    PromptSource("S1", "Altivar Process ATV600 Programming Manual", "ATV600", 672, 672,
                 "Error codes > OHF [Device Overheat]", "fault", "Fault code OHF: Device Overheat"),
    PromptSource("S2", "Altivar Process ATV600 Programming Manual", "ATV600", 12, 13,
                 "About The Document", "safety", "DANGER Disconnect all power"),
]


def test_prompt_lists_sources_with_ids_pages_and_kind():
    text = build_user_prompt("OHF on pump", SOURCES, machine="DEMO-PUMP-01 (ATV600)")
    assert '<source id="S1" model="ATV600"' in text
    assert 'pages="p.672"' in text and 'pages="pp.12-13"' in text
    assert 'kind="safety"' in text
    assert "MACHINE: DEMO-PUMP-01 (ATV600)" in text
    assert text.rstrip().endswith("OHF on pump")
    assert "<telemetry>" not in text


def test_telemetry_block_appears_only_when_there_are_readings():
    readings = [Reading(datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc), "motor_current", 12.5, "A")]
    assert "<telemetry>" not in build_user_prompt("q", SOURCES, telemetry=[])
    text = build_user_prompt("q", SOURCES, telemetry=readings)
    assert "<telemetry>" in text and "motor_current=12.5 A" in text


def test_system_prompt_states_the_grounding_rules():
    for phrase in ("source_ids", "insufficient_evidence", "requires_isolation", "Never mention a fault code"):
        assert phrase in SYSTEM_PROMPT


def test_recognised_codes_and_lookalikes_are_listed_for_the_llm():
    line = "InFI (atv12 p.111): the operator typed 'InF1', which looks the same on the drive's 7-segment display"
    text = build_user_prompt("fan says InF1", SOURCES, recognised_codes=[line])
    assert "RECOGNISED FAULT CODES:" in text and line in text
    assert "RECOGNISED FAULT CODES:" not in build_user_prompt("q", SOURCES, recognised_codes=[])


def test_system_prompt_lists_several_fitting_causes_instead_of_refusing():
    assert 'Use status "insufficient_evidence" only when the SOURCES do not describe' in SYSTEM_PROMPT
    assert "RECOGNISED FAULT CODES" in SYSTEM_PROMPT
