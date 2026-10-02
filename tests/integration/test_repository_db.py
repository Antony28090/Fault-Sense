import numpy as np
import pytest

from helpers import sample_extracted
from faultsense.db.repository import Repository

pytestmark = pytest.mark.db


def _vectors(n):
    return np.eye(n, 1024, dtype=np.float32)


def test_replace_manual_roundtrip_and_searches(db_conn):
    repo = Repository(db_conn)
    ex = sample_extracted()
    repo.replace_manual(ex, _vectors(len(ex.chunks)))
    fault_id = ex.chunks[1].id
    assert repo.manual_hashes() == {"m1": ex.sha256}
    assert repo.keyword_search("drive overheating ambient temperature", None, 5)[0][0] == fault_id
    assert repo.vector_search(_vectors(3)[1], ["m1"], 2)[0][0] == fault_id
    assert repo.vector_search(_vectors(3)[1], ["other"], 2) == []
    assert repo.fault_index()["OHF"][0].chunk_id == fault_id
    assert [c.kind for c in repo.safety_chunks(["m1"])] == ["safety"]
    assert repo.get_chunks([fault_id])[fault_id].page_start == 10
    codes, labels = repo.known_identifiers()
    assert {"OHF", "CLI"} <= codes and "current limitation" in labels


def test_replace_manual_does_not_duplicate(db_conn):
    repo = Repository(db_conn)
    repo.replace_manual(sample_extracted(), _vectors(3))
    repo.replace_manual(sample_extracted(sha="b" * 64, section_text="Rewired."), _vectors(3))
    assert db_conn.execute("select count(*) from chunks").fetchone()[0] == 3
    assert repo.manual_hashes() == {"m1": "b" * 64}
    assert repo.keyword_search("rewired", ["m1"], 5)[0][0] == "m1:s00000"


def test_vector_search_can_be_limited_to_fault_chunks(db_conn):
    repo = Repository(db_conn)
    ex = sample_extracted()
    repo.replace_manual(ex, _vectors(len(ex.chunks)))
    assert [cid for cid, _ in repo.vector_search(_vectors(3)[0], ["m1"], 5, kind="fault")] == [ex.chunks[1].id]


def test_known_identifiers_by_manual(db_conn):
    repo = Repository(db_conn)
    repo.replace_manual(sample_extracted("m1"), _vectors(3))
    by_manual = repo.known_identifiers_by_manual()
    codes, labels = by_manual["m1"]
    assert "OHF" in codes and "current limitation" in labels
