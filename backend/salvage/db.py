"""Storage layer — runs on SQLite (local/demo) or Postgres (cloud).

Why both: SQLite makes the demo reliable and account-free; Postgres is required
for real cloud deployment, because cloud filesystems are ephemeral (a container
restart would erase a SQLite file, taking the audit trail with it). Set
DATABASE_URL to a postgres:// URL and the same code runs unchanged.

The connection wrapper keeps sqlite3's familiar `conn.execute(sql, params)`
shape and translates the small number of dialect differences (placeholders,
autoincrement, upserts) in one place, so the rest of the codebase stays plain SQL.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from .config import settings

# Accept our own var first, then the names the Supabase<>Vercel integration
# injects automatically (so connecting that integration needs zero manual config).
#
# Order matters. Supabase's DIRECT connection (db.<ref>.supabase.co:5432) is
# IPv6-only on the free tier, and Vercel's runtime is IPv4-only -- so the direct
# URL is unreachable from a Vercel function. Supabase's documented choice for
# serverless is the Supavisor POOLED connection in transaction mode (port 6543),
# which is IPv4 on every tier. So we prefer pooled URLs and keep the non-pooling
# one only as a last resort (it is the right choice on a normal IPv6-capable VM).
# Transaction mode forbids prepared statements -- see prepare_threshold below.
def _clean(url: str | None) -> str:
    if not url:
        return ""
    url = url.strip()
    # Prisma-style URLs carry ?pgbouncer=true, which libpq does not understand.
    url = re.sub(r"([?&])pgbouncer=true&?", r"\1", url).rstrip("?&")
    return url


DATABASE_URL = (
    _clean(os.getenv("DATABASE_URL"))
    or _clean(os.getenv("POSTGRES_URL"))
    or _clean(os.getenv("POSTGRES_PRISMA_URL"))
    or _clean(os.getenv("POSTGRES_URL_NON_POOLING"))
)
IS_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS events (
    event_id     TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    received_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customers (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    segment               TEXT NOT NULL,
    lifetime_value_paise  BIGINT NOT NULL,
    orders_count          INTEGER NOT NULL,
    days_since_last_order INTEGER NOT NULL,
    incentives_last_30d   INTEGER NOT NULL,
    is_churn_risk         INTEGER NOT NULL,
    is_flagged_abuse      INTEGER NOT NULL,
    contacts_in_window    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS payments (
    id             TEXT PRIMARY KEY,
    order_id       TEXT NOT NULL,
    customer_id    TEXT NOT NULL,
    amount_paise   BIGINT NOT NULL,
    method         TEXT NOT NULL,
    status         TEXT NOT NULL,
    failure_reason TEXT,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recoveries (
    id                TEXT PRIMARY KEY,
    payment_id        TEXT NOT NULL,
    customer_id       TEXT NOT NULL,
    amount_paise      BIGINT NOT NULL,
    root_cause        TEXT NOT NULL,
    llm_provider      TEXT NOT NULL,
    proposed_play     TEXT NOT NULL,
    final_play        TEXT NOT NULL,
    incentive_paise   BIGINT NOT NULL,
    requires_approval INTEGER NOT NULL,
    vetoed            INTEGER NOT NULL,
    status            TEXT NOT NULL,
    in_control_group  INTEGER NOT NULL DEFAULT 0,
    reasons_json      TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    idempotency_key TEXT PRIMARY KEY,
    recovery_id     TEXT NOT NULL,
    kind            TEXT NOT NULL,
    amount_paise    BIGINT NOT NULL,
    status          TEXT NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS executions (
    idempotency_key TEXT PRIMARY KEY,
    recovery_id     TEXT NOT NULL,
    provider        TEXT NOT NULL,
    link_id         TEXT NOT NULL,
    short_url       TEXT NOT NULL,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    recovery_id TEXT,
    stage       TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    prev_hash   TEXT NOT NULL,
    this_hash   TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status);
CREATE INDEX IF NOT EXISTS idx_recoveries_status ON recoveries(status);
CREATE INDEX IF NOT EXISTS idx_audit_recovery ON audit(recovery_id);
"""

# Postgres needs BIGSERIAL instead of INTEGER ... AUTOINCREMENT.
_SCHEMA_PG = _SCHEMA_SQLITE.replace(
    "seq         INTEGER PRIMARY KEY AUTOINCREMENT", "seq         BIGSERIAL PRIMARY KEY"
)

SCHEMA = _SCHEMA_PG if IS_PG else _SCHEMA_SQLITE


def _translate(sql: str) -> str:
    """Rewrite SQLite-flavoured SQL for Postgres, so every call site stays plain
    SQLite SQL. Handles the two upsert idioms and both placeholder styles."""
    if not IS_PG:
        return sql

    m_ignore = re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO\s+(\w+)\s*\(([^)]*)\)", sql, re.I)
    m_replace = re.match(r"\s*INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]*)\)", sql, re.I)
    if m_ignore:
        sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, flags=re.I)
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    elif m_replace:
        cols = [c.strip() for c in m_replace.group(2).split(",")]
        pk = cols[0]  # by convention the first column is the primary key here
        updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != pk)
        sql = re.sub(r"INSERT\s+OR\s+REPLACE\s+INTO", "INSERT INTO", sql, flags=re.I)
        sql = sql.rstrip().rstrip(";") + f" ON CONFLICT ({pk}) DO UPDATE SET {updates}"

    # Named placeholders (:name -> %(name)s), then positional (? -> %s).
    sql = re.sub(r":(\w+)", r"%(\1)s", sql)
    sql = sql.replace("?", "%s")
    return sql


class _Cursor:
    """Minimal cursor facade so call sites keep using .fetchone()/.fetchall()."""

    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur.fetchall())


class Conn:
    """Uniform connection wrapper over sqlite3 / psycopg."""

    def __init__(self, raw, is_pg: bool):
        self._raw = raw
        self.is_pg = is_pg

    def execute(self, sql: str, params=()):
        sql = _translate(sql)
        if self.is_pg:
            cur = self._raw.cursor()
            cur.execute(sql, params)
            return _Cursor(cur)
        return _Cursor(self._raw.execute(sql, params))

    def executemany(self, sql: str, seq):
        sql = _translate(sql)
        if self.is_pg:
            cur = self._raw.cursor()
            cur.executemany(sql, list(seq))
            return _Cursor(cur)
        return _Cursor(self._raw.executemany(sql, seq))

    def executescript(self, script: str):
        if self.is_pg:
            cur = self._raw.cursor()
            cur.execute(script)
            return
        self._raw.executescript(script)

    def close(self):
        self._raw.close()


def _ipv4_hostaddr(host: str, port: int) -> str | None:
    """Resolve `host` to a single IPv4 address, or None if it has no A record.

    psycopg3 does its own dual-stack (AF_UNSPEC) hostname resolution inside
    conninfo_attempts, which fails on Vercel/Lambda with
    'OperationalError: [Errno 16] Device or resource busy'. We resolve to IPv4
    ourselves and hand psycopg a `hostaddr`, so it skips that path entirely.
    Forcing IPv4 also matters because Vercel's runtime is IPv4-only while
    Supabase's DIRECT endpoint is IPv6-only (the pooler is IPv4)."""
    import socket

    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return None
    return infos[0][4][0] if infos else None


def connect(db_path: str | None = None) -> Conn:
    if IS_PG:
        from urllib.parse import urlparse

        import psycopg
        from psycopg.rows import dict_row

        # Pre-resolve the host to IPv4 and pass hostaddr, bypassing psycopg3's
        # internal resolver (which raises EBUSY on Vercel). host= is kept for TLS
        # SNI / certificate verification.
        parsed = urlparse(DATABASE_URL)
        kwargs: dict = {}
        if parsed.hostname:
            ipv4 = _ipv4_hostaddr(parsed.hostname, parsed.port or 5432)
            if ipv4:
                kwargs["hostaddr"] = ipv4
            elif os.getenv("VERCEL"):
                # No IPv4 for this host on an IPv4-only runtime -> it will never
                # connect. Fail with an actionable message instead of EBUSY.
                raise RuntimeError(
                    f"DATABASE_URL host '{parsed.hostname}' has no IPv4 address. "
                    "On Vercel use the Supabase Transaction pooler connection "
                    "string (host *.pooler.supabase.com, port 6543)."
                )

        # prepare_threshold=None disables server-side prepared statements, which
        # keeps us compatible with pgbouncer transaction-pooler URLs.
        raw = psycopg.connect(
            DATABASE_URL, autocommit=True, row_factory=dict_row,
            prepare_threshold=None, **kwargs,
        )
        return Conn(raw, True)

    path = db_path or settings.db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(path, timeout=15, isolation_level=None)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA journal_mode=WAL;")
    raw.execute("PRAGMA busy_timeout=8000;")
    return Conn(raw, False)


def init_db(db_path: str | None = None) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()
