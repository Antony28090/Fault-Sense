from faultsense.eval.metrics import ScenarioResult, code_match, hit_at_k, summarize
from faultsense.eval.scenarios import ExpectedSource

EXPECTED = [ExpectedSource(manual="atv600", pages=[672])]


def _item(manual, a, b):
    return {"manual": manual, "page_start": a, "page_end": b, "kind": "fault", "heading": "h", "score": 1.0}


def test_hit_at_k_uses_page_ranges_and_cutoff():
    retrieved = [_item("atv900", 672, 672)] * 5 + [_item("atv600", 671, 673)]
    assert hit_at_k(retrieved, EXPECTED, 5) is False
    assert hit_at_k(retrieved, EXPECTED, 6) is True
    assert hit_at_k(retrieved, [], 5) is None


def test_code_match_accepts_lookalikes_and_case():
    assert code_match(["OLF"], ["OLF"]) is True
    assert code_match(["InFI"], ["INF1"]) is True
    assert code_match(["OHF"], ["OHF", "TJF"]) is False
    assert code_match([], []) is None


def test_summarize_ignores_not_applicable_values():
    results = [
        ScenarioResult("a", "fault_code", False, hit_at_5=True, code_match=True, latency_ms=100),
        ScenarioResult("b", "symptom", False, hit_at_5=False, latency_ms=300),
        ScenarioResult("c", "out_of_scope", True),
    ]
    summary = summarize(results)
    assert (summary["scenarios"], summary["reviewed"], summary["errors"]) == (3, 1, 0)
    assert summary["metrics"]["retrieval_hit_at_5"] == {"value": 0.5, "n": 2}
    assert summary["metrics"]["fault_code_match"] == {"value": 1.0, "n": 1}
    assert summary["metrics"]["cause_in_top_3"] == {"value": None, "n": 0}
    assert summary["metrics"]["citation_accuracy"] == {"value": None, "n": 0}
    assert summary["latency_ms"] == {"p50": 100, "p95": 300}


from faultsense.diagnosis.schema import Cause, Citation, DiagnosisResponse, Meta, SourceRef, Step
from faultsense.embeddings import HashEmbedder
from faultsense.eval.metrics import answer_text, cause_at_3, citation_accuracy


def _ref(sid, page, kind="fault"):
    return SourceRef(id=sid, chunk_id=f"c{sid}", manual="atv600", manual_title="T", family="ATV600",
                     page_start=page, page_end=page, heading="h", kind=kind)


def _cite(sid, page):
    return [Citation(source_id=sid, manual="atv600", manual_title="T", page=page)]


def _response():
    return DiagnosisResponse(
        status="diagnosis", query="q", machine_id=None, language="en", matched_fault_codes=[],
        probable_causes=[Cause(rank=1, cause="Ambient temperature too high.", confidence=0.8, fault_code="OHF", citations=_cite("S1", 672))],
        corrective_actions=[
            Step(step=1, action="Disconnect all power.", requires_isolation=True, citations=_cite("S2", 12)),
            Step(step=2, action="Clean the heat sink.", requires_isolation=True, citations=_cite("S3", 100)),
        ],
        safety_warnings=[], escalation=None, sources=[_ref("S1", 672), _ref("S2", 12, "safety"), _ref("S3", 100)],
        meta=Meta(retrieval_top_score=1.0),
    )


def test_cause_at_3_matches_semantically_close_causes():
    embed = HashEmbedder().embed
    hit, pairs = cause_at_3(["Ambient temperature too high.", "Fan failure."], ["Ambient temperature too high."], embed, 0.75)
    assert hit is True and pairs[0][1] == "Ambient temperature too high." and pairs[0][2] == 1.0
    assert cause_at_3(["Modbus link lost."], ["Ambient temperature too high."], embed, 0.75)[0] is False
    assert cause_at_3([], ["Ambient temperature too high."], embed, 0.75) == (False, [])
    assert cause_at_3(["x"], [], embed, 0.75) == (None, [])


def test_citation_accuracy_skips_the_safety_anchor():
    assert citation_accuracy(_response(), [ExpectedSource(manual="atv600", pages=[672])]) == (1, 2)


def test_answer_text_collects_every_answer_field():
    text = answer_text(_response())
    assert "Ambient temperature too high." in text and "OHF" in text and "Clean the heat sink." in text
