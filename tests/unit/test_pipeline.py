from helpers import sample_extracted
from faultsense.embeddings import HashEmbedder
from faultsense.ingest.pipeline import embedding_text, ingest_manual


class FakeRepo:
    def __init__(self, hashes=None):
        self.hashes = dict(hashes or {})
        self.replaced = []

    def manual_hashes(self):
        return dict(self.hashes)

    def replace_manual(self, ex, embeddings):
        self.replaced.append((ex.spec.id, embeddings.shape))
        self.hashes[ex.spec.id] = ex.sha256


def test_new_manual_is_embedded_and_stored():
    repo = FakeRepo()
    assert ingest_manual(sample_extracted(), repo, HashEmbedder()) == "ingested"
    assert repo.replaced == [("m1", (3, 1024))]


def test_unchanged_manual_is_skipped():
    ex = sample_extracted()
    repo = FakeRepo({"m1": ex.sha256})
    assert ingest_manual(ex, repo, HashEmbedder()) == "unchanged"
    assert repo.replaced == []


def test_force_or_changed_pdf_reingests():
    ex = sample_extracted()
    assert ingest_manual(ex, FakeRepo({"m1": ex.sha256}), HashEmbedder(), force=True) == "ingested"
    assert ingest_manual(ex, FakeRepo({"m1": "old"}), HashEmbedder()) == "ingested"


def test_embedding_text_carries_model_and_heading():
    ex = sample_extracted()
    assert embedding_text("ATV600", ex.chunks[1]).startswith("ATV600 | Error codes > OHF [Drive Overheating]\n")
