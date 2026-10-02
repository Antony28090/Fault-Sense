from types import SimpleNamespace

import psycopg
import pytest

from faultsense.db.repository import Repository


class FakeConn:
    def __init__(self, rows=None, error=None):
        self.rows, self.error, self.closed = rows or [], error, False
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append(sql)
        if self.error:
            raise self.error
        return SimpleNamespace(fetchall=lambda: list(self.rows))

    def close(self):
        self.closed = True


def dropped():
    return psycopg.OperationalError("server closed the connection unexpectedly")


def test_reads_reconnect_once_after_a_dropped_connection():
    dead, fresh = FakeConn(error=dropped()), FakeConn(rows=[("atv12", "abc")])
    repo = Repository(dead, reconnect=lambda: fresh)
    assert repo.manual_hashes() == {"atv12": "abc"}
    assert repo.conn is fresh and dead.closed


def test_a_second_failure_is_raised():
    repo = Repository(FakeConn(error=dropped()), reconnect=lambda: FakeConn(error=dropped()))
    with pytest.raises(psycopg.OperationalError):
        repo.ping()


def test_without_a_reconnect_factory_the_error_is_raised():
    with pytest.raises(psycopg.OperationalError):
        Repository(FakeConn(error=dropped())).manual_hashes()


def test_query_errors_do_not_reconnect():
    calls = []
    repo = Repository(FakeConn(error=psycopg.errors.UndefinedTable("no table")), reconnect=lambda: calls.append(1))
    with pytest.raises(psycopg.errors.UndefinedTable):
        repo.manual_hashes()
    assert calls == []
