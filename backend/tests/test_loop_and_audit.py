"""End-to-end loop over the synthetic hero cases, plus audit-chain integrity."""
from __future__ import annotations

from salvage import agent, audit, outbox
from salvage.enums import Play
from salvage.payments.mock import MockGateway


def _process(conn, payment_id):
    p = conn.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
    event_id = f"evt_{payment_id}"
    conn.execute(
        "INSERT OR IGNORE INTO events (event_id, kind, payload_json, received_at) VALUES (?,?,?,?)",
        (event_id, "payment.failed", "{}", "2026-08-27T00:00:00+00:00"),
    )
    return agent.process_failed_payment(conn, event_id, p)


def test_hero_refuse_is_do_nothing(conn):
    rec = _process(conn, "pay_hero_refuse")
    assert rec["final_play"] == Play.DO_NOTHING.value
    assert rec["incentive_paise"] == 0
    assert rec["vetoed"] == 1


def test_hero_recover_gets_capped_incentive_and_waits_for_approval(conn):
    rec = _process(conn, "pay_hero_recover")
    assert rec["final_play"] == Play.SMALL_INCENTIVE.value
    assert 0 < rec["incentive_paise"] <= 20_000
    # incentive exceeds the ₹100 approval threshold, so a human must approve.
    assert rec["requires_approval"] == 1


def test_hero_bankdown_forces_switch_rail(conn):
    rec = _process(conn, "pay_hero_bankdown")
    assert rec["final_play"] == Play.SWITCH_RAIL.value
    assert rec["incentive_paise"] == 0


def test_processing_is_idempotent_on_event_id(conn):
    first = _process(conn, "pay_hero_bankdown")
    # Re-run with the same event id -> same recovery, no duplicate.
    p = conn.execute("SELECT * FROM payments WHERE id=?", ("pay_hero_bankdown",)).fetchone()
    second = agent.process_failed_payment(conn, "evt_pay_hero_bankdown", p)
    assert first["id"] == second["id"]
    n = conn.execute("SELECT COUNT(*) AS c FROM recoveries WHERE payment_id=?", ("pay_hero_bankdown",)).fetchone()["c"]
    assert n == 1


def test_audit_chain_is_intact_after_a_batch(conn):
    for pid in ("pay_hero_refuse", "pay_hero_recover", "pay_hero_bankdown"):
        _process(conn, pid)
    outbox.run_once(conn, MockGateway())
    ok, broken = audit.verify_chain(conn)
    assert ok is True
    assert broken is None


def test_audit_tampering_is_detected(conn):
    _process(conn, "pay_hero_bankdown")
    # Forge a past audit row's detail. The chain must catch it.
    conn.execute("UPDATE audit SET detail_json='{\"tampered\":true}' WHERE seq=(SELECT MIN(seq) FROM audit)")
    ok, broken = audit.verify_chain(conn)
    assert ok is False
    assert broken is not None
