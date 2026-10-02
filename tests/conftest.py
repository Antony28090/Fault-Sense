"""Shared fixtures. Markers are declared in pyproject.toml."""
from functools import lru_cache

import pytest

from helpers import MANUALS_DIR, SPECS
from faultsense.ingest.pdf_reader import read_pdf


@lru_cache(maxsize=None)
def _read(manual_id: str):
    return read_pdf(SPECS[manual_id].path(MANUALS_DIR))


@pytest.fixture(scope="session")
def manual_doc():
    """Return (spec, PdfDocument) for a manual id; skip when the PDF has not been fetched."""

    def load(manual_id: str):
        spec = SPECS[manual_id]
        if not spec.path(MANUALS_DIR).exists():
            pytest.skip(f"{spec.file} missing: run `faultsense fetch-manuals`")
        return spec, _read(manual_id)

    return load


import uuid


@pytest.fixture
def db_conn():
    """A connection whose search_path points at a throwaway schema, dropped afterwards."""
    from faultsense.config import get_settings
    from faultsense.db.connection import connect, init_db

    url = get_settings().database_url
    if not url:
        pytest.skip("DATABASE_URL is not set")
    schema = f"fs_test_{uuid.uuid4().hex[:8]}"
    conn = connect(url, schema)
    init_db(conn)
    try:
        yield conn
    finally:
        conn.execute(f'drop schema if exists "{schema}" cascade')
        conn.close()
