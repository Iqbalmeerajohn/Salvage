"""Outbox + worker: the exactly-once execution mechanism.

A row in `outbox` means "a money action is intended." The worker is the only
component that performs it. `execute_one` is re-entrant by construction:

  1. If an execution already exists for this idempotency_key -> do nothing but
     mark the outbox row done. (Covers a crash AFTER recording.)
  2. Otherwise call the gateway, then INSERT OR IGNORE into executions. The
     UNIQUE(idempotency_key) constraint means a concurrent or repeated insert
     collapses to one row. (Covers a crash BEFORE recording: the mock gateway is
     deterministic, so the retried call yields the same link id.)

Either way, the number of links created for a recovery is exactly one.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from . import audit
from .payments.base import LinkResult, PaymentGateway

MAX_ATTEMPTS = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enqueue(conn: sqlite3.Connection, recovery_id: str, amount_paise: int, kind: str = "create_recovery_link") -> None:
    # idempotency_key = recovery_id => at most one action per recovery, enforced
    # by the PRIMARY KEY on outbox.idempotency_key.
    conn.execute(
        "INSERT OR IGNORE INTO outbox (idempotency_key, recovery_id, kind, amount_paise, status, attempts, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)",
        (recovery_id, recovery_id, kind, amount_paise, _now(), _now()),
    )


def fetch_pending(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM outbox WHERE status='pending' ORDER BY created_at LIMIT ?", (limit,)
    ).fetchall()


def _existing_execution(conn: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM executions WHERE idempotency_key=?", (key,)
    ).fetchone()


def execute_one(conn: sqlite3.Connection, gateway: PaymentGateway, row: sqlite3.Row) -> LinkResult:
    key = row["idempotency_key"]

    # Step 1: already executed? Then this is a retry after a crash — no new call.
    existing = _existing_execution(conn, key)
    if existing is not None:
        conn.execute(
            "UPDATE outbox SET status='done', updated_at=? WHERE idempotency_key=?", (_now(), key)
        )
        conn.execute("UPDATE recoveries SET status='executed' WHERE id=?", (row["recovery_id"],))
        return LinkResult(existing["provider"], existing["link_id"], existing["short_url"], existing["status"])

    conn.execute(
        "UPDATE outbox SET attempts=attempts+1, updated_at=? WHERE idempotency_key=?", (_now(), key)
    )

    rec = conn.execute("SELECT * FROM recoveries WHERE id=?", (row["recovery_id"],)).fetchone()
    cust = conn.execute("SELECT * FROM customers WHERE id=?", (rec["customer_id"],)).fetchone()

    # Step 2: the single external call.
    result = gateway.create_recovery_link(
        idempotency_key=key,
        amount_paise=row["amount_paise"],
        description=f"Recovery for order {rec['payment_id']}",
        customer_ref=cust["id"] if cust else rec["customer_id"],
    )

    # Step 3: record exactly once. INSERT OR IGNORE => the UNIQUE key wins if a
    # duplicate ever races in.
    conn.execute(
        "INSERT OR IGNORE INTO executions (idempotency_key, recovery_id, provider, link_id, short_url, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (key, row["recovery_id"], result.provider, result.link_id, result.short_url, result.status, _now()),
    )
    conn.execute(
        "UPDATE outbox SET status='done', updated_at=? WHERE idempotency_key=?", (_now(), key)
    )
    conn.execute("UPDATE recoveries SET status='executed' WHERE id=?", (row["recovery_id"],))
    audit.append(conn, "EXECUTE", {
        "idempotency_key": key, "provider": result.provider,
        "link_id": result.link_id, "amount_paise": row["amount_paise"],
    }, recovery_id=row["recovery_id"])
    return result


def run_once(conn: sqlite3.Connection, gateway: PaymentGateway, limit: int = 50) -> int:
    """Process all pending outbox rows. Returns count executed."""
    n = 0
    for row in fetch_pending(conn, limit):
        try:
            execute_one(conn, gateway, row)
            n += 1
        except Exception as exc:
            attempts = row["attempts"] + 1
            status = "dead" if attempts >= MAX_ATTEMPTS else "pending"
            conn.execute(
                "UPDATE outbox SET status=?, updated_at=? WHERE idempotency_key=?",
                (status, _now(), row["idempotency_key"]),
            )
            audit.append(conn, "EXECUTE_FAILED", {
                "idempotency_key": row["idempotency_key"], "attempts": attempts,
                "error": f"{type(exc).__name__}: {exc}", "status": status,
            }, recovery_id=row["recovery_id"])
    return n
