from faultsense.db.repository import FaultHit, StoredChunk
from faultsense.eval.runner import run_eval
from faultsense.eval.scenarios import Scenario
from faultsense.manifest import MachineSpec
from faultsense.retrieval.retriever import CodeMatch, RetrievalResult, RetrievedChunk

MACHINES = {"DEMO-PUMP-01": MachineSpec(id="DEMO-PUMP-01", manual="atv600")}
SCENARIO = Scenario(
    id="s1", type="fault_code", query="OHF on pump", machine_id="DEMO-PUMP-01", expected_behavior="diagnose",
    expected_fault_codes=["OHF"], expected_causes=["x"], expected_sources=[{"manual": "atv600", "pages": [672]}],
)


class FakeRetriever:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def retrieve(self, query, manual_ids=None):
        self.calls.append((query, manual_ids))
        return self.result


def _result():
    chunk = StoredChunk("atv600:f:OHF", "atv600", "fault", "Error codes > OHF", 672, 672, "...")
    match = CodeMatch(FaultHit("atv600", "OHF", "Device Overheat", "atv600:f:OHF", 672), "OHF", False)
    return RetrievalResult("OHF on pump", ["atv600"], [match], [RetrievedChunk(chunk, 1.0, "OHF")])


def test_retrieval_only_run_scores_hit_and_code_match():
    retriever = FakeRetriever(_result())
    [r] = run_eval([SCENARIO], retriever, MACHINES)
    assert retriever.calls == [("OHF on pump", ["atv600"])]
    assert (r.hit_at_5, r.code_match, r.top_score, r.detected_codes) == (True, True, 1.0, ["OHF"])
    assert r.retrieved[0] == {"manual": "atv600", "page_start": 672, "page_end": 672, "kind": "fault",
                              "heading": "Error codes > OHF", "score": 1.0}
    assert r.error is None


def test_errors_are_recorded_and_the_run_continues():
    class Broken:
        def retrieve(self, query, manual_ids=None):
            raise RuntimeError("db down")

    results = run_eval([SCENARIO, SCENARIO.model_copy(update={"id": "s2"})], Broken(), MACHINES)
    assert [r.error for r in results] == ["RuntimeError: db down"] * 2


def test_rewritten_query_is_recorded():
    result = _result()
    result.expanded_query = "device overheating"
    [r] = run_eval([SCENARIO], FakeRetriever(result), MACHINES)
    assert r.expanded_query == "device overheating"


from faultsense.diagnosis.guard import KnownIdentifiers
from faultsense.diagnosis.schema import Cause, Citation, DiagnosisResponse, MatchedCode, Meta, SourceRef
from faultsense.embeddings import HashEmbedder
from faultsense.eval.runner import AnswerScorer

KNOWN = KnownIdentifiers(frozenset({"OHF"}), frozenset())


class FakeService:
    def __init__(self, response):
        self.response = response

    def diagnose(self, query, machine_id=None):
        return self.response


def _diagnosis(cause="Ambient temperature too high.", first_pass=()):
    ref = SourceRef(id="S1", chunk_id="atv600:f:OHF", manual="atv600", manual_title="T", family="ATV600",
                    page_start=672, page_end=672, heading="h", kind="fault")
    citation = Citation(source_id="S1", manual="atv600", manual_title="T", page=672)
    return DiagnosisResponse(
        status="diagnosis", query="q", machine_id="DEMO-PUMP-01", language="en", matched_fault_codes=[],
        probable_causes=[Cause(rank=1, cause=cause, confidence=0.8, fault_code="OHF", citations=[citation])],
        corrective_actions=[], safety_warnings=[], escalation=None, sources=[ref],
        meta=Meta(retrieval_top_score=1.0, llm_called=True, first_pass_violations=list(first_pass), latency_ms=900),
    )


def test_full_run_scores_answers():
    scenario = SCENARIO.model_copy(update={"expected_causes": ["Ambient temperature too high."]})
    scorer = AnswerScorer(HashEmbedder().embed, KNOWN, 0.75)
    [r] = run_eval([scenario], FakeRetriever(_result()), MACHINES, FakeService(_diagnosis()), scorer)
    assert (r.status, r.cause_at_3, r.citations_correct, r.citations_total) == ("diagnosis", True, 1, 1)
    assert (r.false_escalation, r.final_hallucination, r.raw_hallucination) == (False, False, False)
    assert r.latency_ms == 900 and r.answer["status"] == "diagnosis"


def test_hallucinations_before_and_after_the_guard_are_counted():
    scorer = AnswerScorer(HashEmbedder().embed, KNOWN, 0.75)
    first_pass = ["cause 1: unknown identifier XQZ7"]
    [clean] = run_eval([SCENARIO], FakeRetriever(_result()), MACHINES, FakeService(_diagnosis(first_pass=first_pass)), scorer)
    assert (clean.raw_hallucination, clean.final_hallucination) == (True, False)
    [dirty] = run_eval([SCENARIO], FakeRetriever(_result()), MACHINES, FakeService(_diagnosis("Check OHF9 wiring.")), scorer)
    assert dirty.final_hallucination is True and dirty.unknown_identifiers == ["OHF9"]


def test_out_of_scope_refusal_is_scored():
    oos = Scenario(id="o", type="out_of_scope", query="weather?", expected_behavior="escalate")
    escalated = _diagnosis().model_copy(update={"status": "escalate", "probable_causes": []})
    scorer = AnswerScorer(HashEmbedder().embed, KNOWN, 0.75)
    [r] = run_eval([oos], FakeRetriever(_result()), MACHINES, FakeService(escalated), scorer)
    assert r.refusal_correct is True and r.false_escalation is None and r.cause_at_3 is None


def test_known_identifiers_can_follow_the_answers_manuals():
    seen = []

    def known_for(manuals):
        seen.append(manuals)
        return KnownIdentifiers(frozenset(), frozenset())

    scorer = AnswerScorer(HashEmbedder().embed, known_for, 0.75)
    [r] = run_eval([SCENARIO], FakeRetriever(_result()), MACHINES, FakeService(_diagnosis()), scorer)
    assert seen == [["atv600"]] and r.unknown_identifiers == ["OHF"]


def test_full_run_scores_retrieval_from_the_diagnosis_without_searching_twice():
    response = _diagnosis()
    response.sources[0].score = 1.0
    response.sources.append(SourceRef(id="S2", chunk_id="atv600:s00010", manual="atv600", manual_title="T",
                                      family="ATV600", page_start=12, page_end=12, heading="Safety", kind="safety"))
    response.matched_fault_codes = [MatchedCode(code="OHF", manual="atv600", name="Device Overheat", page=672)]
    response.meta.search_query = None
    retriever = FakeRetriever(_result())
    scorer = AnswerScorer(HashEmbedder().embed, KNOWN, 0.75)
    [r] = run_eval([SCENARIO], retriever, MACHINES, FakeService(response), scorer)
    assert retriever.calls == []
    assert (r.hit_at_5, r.code_match, r.top_score, r.detected_codes) == (True, True, 1.0, ["OHF"])
    assert r.retrieved == [{"manual": "atv600", "page_start": 672, "page_end": 672, "kind": "fault",
                            "heading": "h", "score": 1.0}]
