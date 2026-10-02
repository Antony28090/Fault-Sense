import pytest

from faultsense.db.connection import connect, schema_sql


def test_missing_database_url_gives_a_clear_error():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        connect("")


def test_schema_name_is_validated_before_connecting():
    with pytest.raises(ValueError, match="invalid schema"):
        connect("postgresql://unused", "bad-name;drop")


def test_schema_sql_defines_the_four_tables():
    sql = schema_sql()
    for table in ("manuals", "chunks", "fault_codes", "lexicon"):
        assert f"create table if not exists {table}" in sql
