from faultsense.db.repository import FaultHit, StoredChunk
from faultsense.embeddings import HashEmbedder
from faultsense.retrieval.fusion import rrf
from faultsense.retrieval.rerank import OverlapReranker
from faultsense.retrieval.retriever import HybridRetriever


def chunk(cid, manual="m600", text="", kind="section"):
    return StoredChunk(cid, manual, kind, f"Heading {cid}", 1, 1, text)


def hit(code, manual="m600", page=1):
    return FaultHit(manual, code, f"name {code}", f"{manual}:f:{code.upper()}", page)


class FakeBackend:
    def __init__(self, chunks, faults=None, keyword=(), vector=()):
        self.chunks = {c.id: c for c in chunks}
        self.faults = faults or {}
        self.keyword, self.vector = list(keyword), list(vector)
        self.calls = []

    def _filter(self, ids, manual_ids, limit, kind=None):
        return [(i, 1.0) for i in ids
                if (manual_ids is None or self.chunks[i].manual_id in manual_ids)
                and (kind is None or self.chunks[i].kind == kind)][:limit]

    def fault_index(self):
        return self.faults

    def keyword_search(self, query, manual_ids, limit):
        self.calls.append(("keyword", manual_ids))
        return self._filter(self.keyword, manual_ids, limit)

    def vector_search(self, embedding, manual_ids, limit, kind=None):
        self.calls.append(("vector", manual_ids) if kind is None else ("vector", manual_ids, kind))
        return self._filter(self.vector, manual_ids, limit, kind)

    def get_chunks(self, ids):
        return {i: self.chunks[i] for i in ids if i in self.chunks}


def retriever(backend, top_k=8):
    return HybridRetriever(backend, HashEmbedder(), OverlapReranker(), top_k=top_k)


def test_rrf_orders_by_fused_rank():
    assert [item for item, _ in rrf([["a", "b", "c"], ["c", "a", "d"]])] == ["a", "c", "b", "d"]


def test_exact_code_is_pinned_first_with_full_score():
    backend = FakeBackend(
        [chunk("m600:f:OHF", kind="fault", text="Device overheating"), chunk("s1", text="fans"), chunk("s2", text="modbus")],
        faults={"OHF": [hit("OHF")]}, keyword=["s1", "s2"], vector=["s2", "s1"],
    )
    result = retriever(backend).retrieve("Drive shows OHF.")
    first = result.chunks[0]
    assert (first.chunk.id, first.score, first.code) == ("m600:f:OHF", 1.0, "OHF")
    assert result.matched_codes[0].fuzzy is False
    assert result.top_score == 1.0
    assert len(result.chunks) == 3


def test_detect_codes_tolerates_punctuation_and_lookalikes():
    backend = FakeBackend([], faults={"OHF": [hit("OHF")], "OLF": [hit("OLF")]})
    r = retriever(backend)
    assert [(m.hit.code, m.fuzzy) for m in r.detect_codes("Drive shows OHF.")] == [("OHF", False)]
    assert [(m.hit.code, m.fuzzy) for m in r.detect_codes("(0hf) again")] == [("OHF", True)]
    assert [(m.hit.code, m.fuzzy) for m in r.detect_codes("0LF on the pump")] == [("OLF", True)]
    assert r.detect_codes("XQZ7 on the pump") == []


def test_exact_match_beats_lookalike_inside_each_manual():
    faults = {
        "INF1": [hit("INF1", "m320"), hit("INF1", "m900")],
        "INFI": [hit("InFI", "m12"), hit("INFI", "m900")],
    }
    matches = retriever(FakeBackend([], faults=faults)).detect_codes("fan says InF1")
    assert {(m.hit.manual_id, m.hit.code, m.fuzzy) for m in matches} == {
        ("m320", "INF1", False), ("m900", "INF1", False), ("m12", "InFI", True),
    }


def test_manual_filter_is_passed_to_every_search():
    backend = FakeBackend(
        [chunk("m600:f:OHF", "m600", kind="fault"), chunk("m320:f:OHF", "m320", kind="fault"),
         chunk("a", "m600", "x"), chunk("b", "m320", "y")],
        faults={"OHF": [hit("OHF", "m600"), hit("OHF", "m320")]},
        keyword=["a", "b"], vector=["b", "a"],
    )
    result = retriever(backend).retrieve("OHF", ["m320"])
    assert backend.calls == [("keyword", ["m320"]), ("vector", ["m320"])]
    assert {c.chunk.manual_id for c in result.chunks} == {"m320"}
    assert [m.hit.manual_id for m in result.matched_codes] == ["m320"]


def test_reranker_orders_the_rest_and_top_k_applies():
    backend = FakeBackend(
        [chunk("s1", text="fan ventilation heat"), chunk("s2", text="modbus link"), chunk("s3", text="heat sink cleaning")],
        keyword=["s2", "s1", "s3"], vector=["s2", "s3", "s1"],
    )
    result = retriever(backend, top_k=2).retrieve("heat fan")
    assert [c.chunk.id for c in result.chunks] == ["s1", "s3"]
    assert result.top_score == 1.0


class FakeRewriter:
    def __init__(self, rewritten):
        self.rewritten = rewritten
        self.calls = []

    def rewrite(self, query):
        self.calls.append(query)
        return self.rewritten


class RecordingReranker(OverlapReranker):
    def __init__(self):
        self.queries = []

    def score(self, query, passages):
        self.queries.append(query)
        return super().score(query, passages)


def test_rewriter_is_not_called_when_a_code_was_typed():
    backend = FakeBackend([chunk("m600:f:OHF", kind="fault")], faults={"OHF": [hit("OHF")]})
    rewriter = FakeRewriter("device overheating")
    result = HybridRetriever(backend, HashEmbedder(), OverlapReranker(), rewriter=rewriter).retrieve("OHF on pump")
    assert rewriter.calls == [] and result.expanded_query is None
    assert ("vector", None, "fault") not in backend.calls


def test_rewritten_query_drives_extra_searches_and_the_reranker():
    backend = FakeBackend([chunk("s1", text="heat sink"), chunk("s2", text="modbus")], keyword=["s1", "s2"], vector=["s2", "s1"])
    reranker = RecordingReranker()
    retriever = HybridRetriever(backend, HashEmbedder(), reranker, rewriter=FakeRewriter("device overheating heat"))
    result = retriever.retrieve("pump trips on hot afternoons")
    assert result.expanded_query == "device overheating heat"
    assert backend.calls.count(("keyword", None)) == 2 and backend.calls.count(("vector", None)) == 2
    assert reranker.queries == ["device overheating heat"]


def test_failed_rewrite_falls_back_to_the_original_query():
    backend = FakeBackend([chunk("s1", text="heat fan")], keyword=["s1"], vector=["s1"])
    result = HybridRetriever(backend, HashEmbedder(), OverlapReranker(), rewriter=FakeRewriter(None)).retrieve("heat fan")
    assert result.expanded_query is None and [c.chunk.id for c in result.chunks] == ["s1"]


def test_top_fault_entries_are_reserved_after_the_rerankers_top_two():
    chunks = [chunk(f"s{n}", text="brake logic settings") for n in range(1, 6)]
    chunks += [chunk("f1", kind="fault", text="brake control error"), chunk("f2", kind="fault", text="encoder fault")]
    backend = FakeBackend(chunks, keyword=["s1", "s2", "s3", "s4", "s5"], vector=["f1", "f2", "s1", "s2"])
    result = HybridRetriever(backend, HashEmbedder(), OverlapReranker()).retrieve("brake logic settings")
    assert [c.chunk.id for c in result.chunks][:4] == ["s1", "s2", "f1", "f2"]
    assert ("vector", None, "fault") in backend.calls


def test_common_words_do_not_become_codes_through_lookalikes():
    r = retriever(FakeBackend([], faults={"INF0": [hit("INF0")], "OHF": [hit("OHF")]}))
    assert r.detect_codes("Need some info: pump trips on hot afternoons") == []
    assert r.detect_codes("Info please, the hoist brake won't release") == []
    assert [(m.hit.code, m.fuzzy) for m in r.detect_codes("display shows INFO")] == [("INF0", True)]
    assert [(m.hit.code, m.fuzzy) for m in r.detect_codes("(0hf) again")] == [("OHF", True)]


def test_hyphen_joined_and_spaced_codes_are_detected():
    r = retriever(FakeBackend([], faults={"OHF": [hit("OHF")], "SCF1": [hit("SCF1")]}))
    assert [m.hit.code for m in r.detect_codes("OHF-fault on the pump")] == ["OHF"]
    assert [m.hit.code for m in r.detect_codes("drive shows SCF 1")] == ["SCF1"]
