from helpers import make_doc, span
from faultsense.ingest.faults import FaultRecord
from faultsense.ingest.lexicon import build_lexicon


def test_lexicon_collects_hmi_codes_tokens_labels_and_faults():
    doc = make_doc({1: [
        [span("Set "), span("[Current Limitation]"), span(" CLI", "CourierNewPS-BoldMT")],
        "Reduce SFr to 4 kHz",
    ]})
    fault = FaultRecord("m1", "OHF", "Device Overheat", "", ["x"], ["y"], "", 1, 1, "block")
    entries = {(e.kind, e.code_key): e for e in build_lexicon(doc, "m1", [fault])}
    assert entries[("hmi", "CLI")].label == "Current Limitation"
    assert ("token", "SFR") in entries
    assert ("label", "current limitation") in entries
    assert entries[("fault", "OHF")].label == "Device Overheat"
    assert entries[("hmi", "CLI")].first_page == 1


def test_fault_names_are_known_labels_even_when_printed_without_brackets():
    doc = make_doc({1: ["Motor or Ground short circuit"]})
    fault = FaultRecord("m1", "SCF1", "Motor or Ground short circuit", "", ["x"], ["y"], "", 1, 1, "table4")
    keys = {(e.kind, e.code_key) for e in build_lexicon(doc, "m1", [fault])}
    assert ("label", "motor or ground short circuit") in keys
