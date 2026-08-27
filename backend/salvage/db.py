"""SQLite persistence layer.

Chosen for the demo because it needs no account, no network, and no server —
the whole recovery loop runs offline and identically every time, which is the
reliability property the submission is built around. The schema is deliberately
plain SQL that ports to Postgres/Supabase for production (see ROADMAP.md).

Concurrency note: WAL mode + a short busy timeout let the API and the worker
touch the same file safely for a single-node demo.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import settings

SCHEMA = """
-- Raw inbound webhook events. Dedup key = razorpay event id.
CREATE TABLE IF NOT EXISTS events (
    event_id     TEXT PRIMARY KEY,          -- razorpay 'x-razorpay-event-id' / payload id
    kind         TEXT NOT NULL,             -- e.g. 'payment.failed'
    payload_json TEXT NOT NULL,
    received_at  TEXT NOT NULL
);

-- Synthetic merchant data (loaded from data/*.json).
CREATE TABLE IF NOT EXISTS customers (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    segment              TEXT NOT NULL,
    lifetime_value_paise INTEGER NOT NULL,
    orders_count         INTEGER NOT NULL,
    days_since_last_order INTEGER NOT NULL,
    incentives_last_30d  INTEGER NOT NULL,
    is_churn_risk        INTEGER NOT NULL,
    is_flagged_abuse     INTEGER NOT NULL,
    contacts_in_window   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS payments (
    id             TEXT PRIMARY KEY,
    order_id       TEXT NOT NULL,
    customer_id    TEXT NOT NULL,
    amount_paise   INTEGER NOT NULL,
    method         TEXT NOT NULL,
    status         TEXT NOT NULL,           -- captured | failed
    failure_reason TEXT,
    created_at     TEXT NOT NULL
);

-- One recovery decision per processed failed payment.
CREATE TABLE IF NOT EXISTS recoveries (
    id                TEXT PRIMARY KEY,      -- = event_id
    payment_id        TEXT NOT NULL,
    customer_id       TEXT NOT NULL,
    amount_paise      INTEGER NOT NULL,
    root_cause        TEXT NOT NULL,
    llm_provider      TEXT NOT NULL,         -- mock | gemini | local  (never lies)
    proposed_play     TEXT NOT NULL,
    final_play        TEXT NOT NULL,
    incentive_paise   INTEGER NOT NULL,
    requires_approval INTEGER NOT NULL,
    vetoed            INTEGER NOT NULL,
    status            TEXT NOT NULL,         -- decided | awaiting_approval | executing | executed | skipped | failed
    in_control_group  INTEGER NOT NULL DEFAULT 0,
    reasons_json      TEXT NOT NULL,
    created_at        TEXT NOT NULL
);

-- Outbox: the exactly-once execution queue. A row here means "money action
-- intended"; the worker is the only thing that performs it.
CREATE TABLE IF NOT EXISTS outbox (
    idempotency_key TEXT PRIMARY KEY,        -- = recovery id; guarantees one action per recovery
    recovery_id     TEXT NOT NULL,
    kind            TEXT NOT NULL,           -- create_recovery_link
    amount_paise    INTEGER NOT NULL,
    status          TEXT NOT NULL,           -- pending | done | dead
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Executions: the record that a money action really happened. UNIQUE on the
-- idempotency key is the hard guarantee that a link is created at most once.
CREATE TABLE IF NOT EXISTS executions (
    idempotency_key TEXT PRIMARY KEY,
    recovery_id     TEXT NOT NULL,
    provider        TEXT NOT NULL,           -- mock | razorpay
    link_id         TEXT NOT NULL,
    short_url       TEXT NOT NULL,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

-- Hash-chained audit log. Append-only; each row's hash covers the previous.
CREATE TABLE IF NOT EXISTS audit (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    recovery_id TEXT,
    stage      TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    prev_hash  TEXT NOT NULL,
    this_hash  TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or settings.db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: str | None = None) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()
