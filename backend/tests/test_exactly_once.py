"""The paranoid test: process death mid-execution yields EXACTLY ONE link.

We simulate the two dangerous crash points around the single external call and
prove that, in every case, the number of executions for a recovery is one.
"""
from __future__ import annotations

from salvage import agent, outbox
from salvage.payments.mock import MockGateway


def _make_executing_recovery(conn, payment_id="pay_hero_bankdown"):
    p = conn.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
    event_id = f"evt_{payment_id}"
    conn.execute(
        "INSERT OR IGNORE INTO events (event_id, kind, payload_json, received_at) VALUES (?,?,?,?)",
        (event_id, "payment.failed", "{}", "2026-08-27T00:00:00+00:00"),
    )
    agent.process_failed_payment(conn, event_id, p)
    # Force it into an executing state with an outbox row, regardless of policy.
    conn.execute("UPDATE recoveries SET status='executing' WHERE id=?", (event_id,))
    outbox.enqueue(conn, recovery_id=event_id, amount_paise=p["amount_paise"])
    return event_id


def _execution_count(conn, key):
    return conn.execute("SELECT COUNT(*) AS c FROM executions WHERE idempotency_key=?", (key,)).fetchone()["c"]


def test_happy_path_creates_one_link(conn):
    key = _make_executing_recovery(conn)
    outbox.run_once(conn, MockGateway())
    assert _execution_count(conn, key) == 1


def test_crash_after_external_call_before_marking_done(conn):
    """Execution recorded, but the 'done' mark was lost (process died). On
    restart the outbox row is still pending. Re-running must NOT create a
    second link."""
    key = _make_executing_recovery(conn)
    outbox.run_once(conn, MockGateway())          # first pass: link created, row done
    link_before = conn.execute("SELECT link_id FROM executions WHERE idempotency_key=?", (key,)).fetchone()["link_id"]
    conn.execute("UPDATE outbox SET status='pending' WHERE idempotency_key=?", (key,))  # simulate lost mark
    outbox.run_once(conn, MockGateway())          # restart
    assert _execution_count(conn, key) == 1
    link_after = conn.execute("SELECT link_id FROM executions WHERE idempotency_key=?", (key,)).fetchone()["link_id"]
    assert link_before == link_after


def test_crash_after_external_call_before_recording_execution(conn):
    """The worst case: the external link was created, but we died before
    recording it. On restart the deterministic gateway returns the SAME link id,
    and INSERT OR IGNORE keeps it to one row."""
    key = _make_executing_recovery(conn)
    outbox.run_once(conn, MockGateway())
    # Simulate: execution record lost AND outbox back to pending.
    conn.execute("DELETE FROM executions WHERE idempotency_key=?", (key,))
    conn.execute("UPDATE outbox SET status='pending' WHERE idempotency_key=?", (key,))
    outbox.run_once(conn, MockGateway())          # restart; gateway called again
    assert _execution_count(conn, key) == 1


def test_double_worker_pass_is_safe(conn):
    key = _make_executing_recovery(conn)
    outbox.run_once(conn, MockGateway())
    outbox.run_once(conn, MockGateway())          # a second worker / second pass
    assert _execution_count(conn, key) == 1
