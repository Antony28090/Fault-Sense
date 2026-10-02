"""All SQL lives here: atomic per-manual writes and the retriever's three searches."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Sequence

import numpy as np
import psycopg
from psycopg.types.json import Jsonb

from faultsense.ingest.faults import fault_chunk_id

if TYPE_CHECKING:
    from faultsense.ingest.extract import ExtractedManual


@dataclass(frozen=True)
class StoredChunk:
    id: str
    manual_id: str
    kind: str
    heading_path: str
    page_start: int
    page_end: int
    text: str


@dataclass(frozen=True)
class FaultHit:
    manual_id: str
    code: str
    name: str
    chunk_id: str
    page: int


_CHUNK_COLUMNS = "id, manual_id, kind, heading_path, page_start, page_end, text"

# OR of the query's lexemes: websearch_to_tsquery ANDs every word, which returns nothing for
# long symptom descriptions such as "drive trips after 10 minutes on hot afternoons".
_KEYWORD_SQL = """
with q as (select replace(plainto_tsquery('english', %(q)s)::text, ' & ', ' | ')::tsquery as tsq)
select c.id, ts_rank_cd(c.tsv, q.tsq) as score
from chunks c, q
where c.tsv @@ q.tsq {filter}
order by score desc, c.id
limit %(k)s
"""


class Repository:
    def __init__(self, conn: psycopg.Connection, reconnect: Callable[[], psycopg.Connection] | None = None):
        self.conn = conn
        self._reconnect = reconnect

    def _read(self, sql: str, params=None) -> list[tuple]:
        """Runs a read query; after a dropped connection (pooler restart, network blip) it reconnects once."""
        try:
            return self.conn.execute(sql, params).fetchall()
        except (psycopg.OperationalError, psycopg.InterfaceError):
            if self._reconnect is None:
                raise
        try:
            self.conn.close()
        except psycopg.Error:
            pass
        self.conn = self._reconnect()
        return self.conn.execute(sql, params).fetchall()

    def ping(self) -> bool:
        self._read("select 1")
        return True

    def manual_hashes(self) -> dict[str, str]:
        return dict(self._read("select id, sha256 from manuals"))

    def replace_manual(self, ex: ExtractedManual, embeddings: np.ndarray) -> None:
        if len(embeddings) != len(ex.chunks):
            raise ValueError(f"{len(ex.chunks)} chunks but {len(embeddings)} embeddings")
        spec = ex.spec
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute("delete from manuals where id = %s", (spec.id,))
            cur.execute(
                "insert into manuals (id, family, title, doc_ref, version, file_name, sha256, page_count)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (spec.id, spec.family, spec.title, spec.doc_ref, spec.version, spec.file, ex.sha256, ex.page_count),
            )
            cur.executemany(
                f"insert into chunks ({_CHUNK_COLUMNS}, embedding) values (%s, %s, %s, %s, %s, %s, %s, %s)",
                [(c.id, c.manual_id, c.kind, c.heading_path, c.page_start, c.page_end, c.text,
                  np.asarray(vector, dtype=np.float32)) for c, vector in zip(ex.chunks, embeddings)],
            )
            cur.executemany(
                "insert into fault_codes (manual_id, code, code_key, name, description, causes, remedies,"
                " clearing, page, page_end, layout, shared_with, chunk_id)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [(f.manual_id, f.code, f.code_key, f.name, f.description, Jsonb(f.causes), Jsonb(f.remedies),
                  f.clearing, f.page, f.page_end, f.layout, list(f.shared_with), fault_chunk_id(f))
                 for f in ex.faults],
            )
            cur.executemany(
                "insert into lexicon (manual_id, kind, code, code_key, label, first_page)"
                " values (%s, %s, %s, %s, %s, %s)",
                [(e.manual_id, e.kind, e.code, e.code_key, e.label, e.first_page) for e in ex.lexicon],
            )

    def fault_index(self) -> dict[str, list[FaultHit]]:
        index: dict[str, list[FaultHit]] = {}
        rows = self._read(
            "select code_key, manual_id, code, name, chunk_id, page from fault_codes order by manual_id, code_key"
        )
        for key, manual_id, code, name, chunk_id, page in rows:
            index.setdefault(key, []).append(FaultHit(manual_id, code, name, chunk_id, page))
        return index

    def keyword_search(self, query: str, manual_ids: list[str] | None, limit: int) -> list[tuple[str, float]]:
        sql = _KEYWORD_SQL.format(filter="and c.manual_id = any(%(m)s)" if manual_ids else "")
        rows = self._read(sql, {"q": query, "m": manual_ids, "k": limit})
        return [(row[0], float(row[1])) for row in rows]

    def vector_search(self, embedding: Sequence[float], manual_ids: list[str] | None, limit: int,
                      kind: str | None = None) -> list[tuple[str, float]]:
        conditions = (["manual_id = any(%(m)s)"] if manual_ids else []) + (["kind = %(kind)s"] if kind else [])
        where = ("where " + " and ".join(conditions)) if conditions else ""
        sql = (f"select id, 1 - (embedding <=> %(e)s) as score from chunks {where} "
               f"order by embedding <=> %(e)s limit %(k)s")
        params = {"e": np.asarray(embedding, dtype=np.float32), "m": manual_ids, "k": limit, "kind": kind}
        return [(row[0], float(row[1])) for row in self._read(sql, params)]

    def get_chunks(self, ids: Sequence[str]) -> dict[str, StoredChunk]:
        if not ids:
            return {}
        rows = self._read(f"select {_CHUNK_COLUMNS} from chunks where id = any(%s)", (list(ids),))
        return {row[0]: StoredChunk(*row) for row in rows}

    def safety_chunks(self, manual_ids: Sequence[str]) -> list[StoredChunk]:
        if not manual_ids:
            return []
        rows = self._read(
            f"select {_CHUNK_COLUMNS} from chunks where kind = 'safety' and manual_id = any(%s)"
            " order by manual_id, page_start, id",
            (list(manual_ids),),
        )
        return [StoredChunk(*row) for row in rows]

    def known_identifiers_by_manual(self) -> dict[str, tuple[set[str], set[str]]]:
        by_manual: dict[str, tuple[set[str], set[str]]] = {}
        for manual_id, kind, key in self._read("select manual_id, kind, code_key from lexicon"):
            codes, labels = by_manual.setdefault(manual_id, (set(), set()))
            (labels if kind == "label" else codes).add(key)
        return by_manual

    def known_identifiers(self) -> tuple[set[str], set[str]]:
        codes: set[str] = set()
        labels: set[str] = set()
        for kind, key in self._read("select kind, code_key from lexicon"):
            (labels if kind == "label" else codes).add(key)
        return codes, labels
