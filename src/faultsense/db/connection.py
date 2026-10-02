"""Connections to Supabase Postgres (session pooler) with pgvector registered."""
from __future__ import annotations

import re
from importlib.resources import files

import psycopg
from pgvector.psycopg import register_vector

_SCHEMA_NAME_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}")


def schema_sql() -> str:
    return files("faultsense.db").joinpath("schema.sql").read_text(encoding="utf-8")


def connect(database_url: str, schema: str = "public") -> psycopg.Connection:
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Put your Supabase session-pooler URI in .env "
            "(README, 'Supabase setup')."
        )
    if not _SCHEMA_NAME_RE.fullmatch(schema):
        raise ValueError(f"invalid schema name {schema!r}")
    # prepare_threshold=None: no server-side prepared statements, which poolers may not support.
    conn = psycopg.connect(database_url, autocommit=True, prepare_threshold=None, connect_timeout=15)
    conn.execute("create extension if not exists vector with schema public")
    conn.execute(f'create schema if not exists "{schema}"')
    conn.execute(f'set search_path to "{schema}", public, extensions')
    register_vector(conn)
    return conn


def init_db(conn: psycopg.Connection) -> None:
    for statement in schema_sql().split(";"):
        if statement.strip():
            conn.execute(statement)
