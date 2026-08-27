"""The recovery agent — the 9-stage loop, orchestrated.

  OBSERVE  -> features already persisted by the webhook layer
  REASON   -> router.diagnose (Gemini/local/mock), enum output only
  PLAN     -> the proposed play (part of the diagnosis)
  POLICY   -> decide(): pure function, owns every rupee
  CONTROL  -> 20% deterministic holdout for incremental-lift measurement
  APPROVAL -> spend over threshold / risk waits for a human
  EXECUTE  -> enqueued to the outbox (worker performs it exactly once)
  VERIFY   -> worker confirms link creation; state comes from the gateway
  AUDIT    -> every stage hash-chained

This function makes the DECISION and enqueues execution. It never calls the
payment gateway directly — that boundary is what keeps money in one place.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from . import audit, outbox
from .enums import Play, RootCause
from .llm.router import Router
from .policy import CustomerState, MerchantPolicy, RecoveryContext, decide

CONTROL_GROUP_RATE = 5  # 1 in 5 => 20% holdout


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _in_control_group(customer_id: str) -> bool:
    """Deterministic 20% holdout. Same customer is always in or out, so the
    control/treatment split is stable and honest across runs."""
    h = int(hashlib.sha256(customer_id.encode("utf-8")).hexdigest()[:8], 16)
    return (h % CONTROL_GROUP_RATE) == 0


def _customer_state(row: sqlite3.Row) -> CustomerState:
    return CustomerState(
        lifetime_value_paise=row["lifetime_value_paise"],
        orders_count=row["orders_count"],
        days_since_last_order=row["days_since_last_order"],
        incentives_last_30d=row["incentives_last_30d"],
        is_churn_risk=bool(row["is_churn_risk"]),
        is_flagged_abuse=bool(row["is_flagged_abuse"]),
        contacts_in_window=row["contacts_in_window"],
    )


def process_failed_payment(
    conn: sqlite3.Connection,
    event_id: str,
    payment: sqlite3.Row,
    router: Router | None = None,
    policy: MerchantPolicy | None = None,
) -> dict:
    """Run the decision loop for one failed payment. Idempotent on event_id:
    if a recovery already exists for this event, return it unchanged."""
    router = router or Router()
    policy = policy or MerchantPolicy()

    existing = conn.execute("SELECT * FROM recoveries WHERE id=?", (event_id,)).fetchone()
    if existing is not None:
        return dict(existing)

    customer = conn.execute(
        "SELECT * FROM customers WHERE id=?", (payment["customer_id"],)
    ).fetchone()
    if customer is None:
        raise ValueError(f"unknown customer {payment['customer_id']}")

    cause = payment["failure_reason"] or RootCause.UNKNOWN.value
    features = {
        "failure_reason": cause,
        "amount_paise": payment["amount_paise"],
        "method": payment["method"],
        "segment": customer["segment"],
        "orders_count": customer["orders_count"],
        "days_since_last_order": customer["days_since_last_order"],
        "incentives_last_30d": customer["incentives_last_30d"],
        "is_churn_risk": bool(customer["is_churn_risk"]),
    }

    audit.append(conn, "OBSERVE", {"event_id": event_id, "payment_id": payment["id"], "features": features}, recovery_id=event_id)

    # REASON + PLAN
    diagnosis, notes = router.diagnose(features)
    audit.append(conn, "REASON", {
        "provider": diagnosis.provider, "model": diagnosis.model_name,
        "root_cause": diagnosis.root_cause.value, "proposed_play": diagnosis.proposed_play.value,
        "proposed_incentive_pct": diagnosis.proposed_incentive_pct,
        "fallback_notes": notes,
    }, recovery_id=event_id)

    # POLICY (the pure function — owns money)
    ctx = RecoveryContext(
        amount_paise=payment["amount_paise"],
        root_cause=diagnosis.root_cause,
        proposed_play=diagnosis.proposed_play,
        proposed_incentive_pct=diagnosis.proposed_incentive_pct,
    )
    d = decide(_customer_state(customer), policy, ctx)
    audit.append(conn, "POLICY", {
        "final_play": d.final_play.value, "incentive_paise": d.incentive_paise,
        "requires_approval": d.requires_approval, "vetoed": d.vetoed, "reasons": list(d.reasons),
    }, recovery_id=event_id)

    # CONTROL: holdout customers get no intervention, so we can measure lift.
    in_control = _in_control_group(payment["customer_id"])

    # Decide status.
    if in_control:
        status = "control_skipped"
    elif d.final_play == Play.DO_NOTHING:
        status = "skipped"
    elif d.requires_approval:
        status = "awaiting_approval"
    else:
        status = "executing"

    conn.execute(
        "INSERT INTO recoveries (id, payment_id, customer_id, amount_paise, root_cause, llm_provider, "
        "proposed_play, final_play, incentive_paise, requires_approval, vetoed, status, in_control_group, reasons_json, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            event_id, payment["id"], payment["customer_id"], payment["amount_paise"],
            diagnosis.root_cause.value, diagnosis.provider, diagnosis.proposed_play.value,
            d.final_play.value, d.incentive_paise, int(d.requires_approval), int(d.vetoed),
            status, int(in_control), json.dumps(list(d.reasons)), _now(),
        ),
    )

    # EXECUTE (only when we're actually acting): enqueue to the outbox. The link
    # amount is the original minus any approved incentive discount.
    if status == "executing":
        payable = max(0, payment["amount_paise"] - d.incentive_paise)
        outbox.enqueue(conn, recovery_id=event_id, amount_paise=payable)
        audit.append(conn, "ENQUEUE", {"payable_paise": payable}, recovery_id=event_id)
    else:
        audit.append(conn, "NO_EXECUTE", {"status": status}, recovery_id=event_id)

    return dict(conn.execute("SELECT * FROM recoveries WHERE id=?", (event_id,)).fetchone())


def approve(conn: sqlite3.Connection, recovery_id: str) -> dict:
    """Merchant approves a held recovery -> enqueue execution."""
    rec = conn.execute("SELECT * FROM recoveries WHERE id=?", (recovery_id,)).fetchone()
    if rec is None:
        raise ValueError("no such recovery")
    if rec["status"] != "awaiting_approval":
        return dict(rec)
    payable = max(0, rec["amount_paise"] - rec["incentive_paise"])
    conn.execute("UPDATE recoveries SET status='executing' WHERE id=?", (recovery_id,))
    outbox.enqueue(conn, recovery_id=recovery_id, amount_paise=payable)
    audit.append(conn, "APPROVED", {"payable_paise": payable}, recovery_id=recovery_id)
    return dict(conn.execute("SELECT * FROM recoveries WHERE id=?", (recovery_id,)).fetchone())
