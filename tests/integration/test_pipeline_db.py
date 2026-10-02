import pytest

from helpers import sample_extracted
from faultsense.db.repository import Repository
from faultsense.embeddings import HashEmbedder
from faultsense.ingest.pipeline import ingest_manual

pytestmark = pytest.mark.db


def test_second_ingest_of_the_same_pdf_is_a_noop(db_conn):
    repo = Repository(db_conn)
    assert ingest_manual(sample_extracted(), repo, HashEmbedder()) == "ingested"
    assert ingest_manual(sample_extracted(), repo, HashEmbedder()) == "unchanged"
