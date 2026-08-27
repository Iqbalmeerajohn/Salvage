"""Load the synthetic dataset into the database.

Two sources, in order:
  1. data/*.json if present (local dev — lets you inspect/edit the fixtures).
  2. Otherwise generate it in-process from synth.py.

Because synth.generate() is deterministic (fixed seed), both paths produce the
identical dataset. This removes a deployment fragility: a cloud build that only
ships the `backend/` directory can still seed itself with no data files.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .db import Conn, connect, init_db

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _from_json() -> tuple[list[dict], list[dict]] | None:
    cf, pf = DATA_DIR / "customers.json", DATA_DIR / "payments.json"
    if cf.exists() and pf.exists():
        return (
            json.loads(cf.read_text(encoding="utf-8")),
            json.loads(pf.read_text(encoding="utf-8")),
        )
    return None


def _from_synth() -> tuple[list[dict], list[dict]]:
    from .synth import generate

    ds = generate()
    return ([asdict(c) for c in ds.customers], [asdict(p) for p in ds.payments])


def load(conn: Conn) -> dict[str, int]:
    src = _from_json() or _from_synth()
    customers, payments = src

    conn.executemany(
        "INSERT OR REPLACE INTO customers (id, name, segment, lifetime_value_paise, orders_count, "
        "days_since_last_order, incentives_last_30d, is_churn_risk, is_flagged_abuse, contacts_in_window) "
        "VALUES (:id,:name,:segment,:lifetime_value_paise,:orders_count,:days_since_last_order,"
        ":incentives_last_30d,:is_churn_risk,:is_flagged_abuse,:contacts_in_window)",
        [
            {
                "id": c["id"], "name": c["name"], "segment": c["segment"],
                "lifetime_value_paise": c["lifetime_value_paise"],
                "orders_count": c["orders_count"],
                "days_since_last_order": c["days_since_last_order"],
                "incentives_last_30d": c["incentives_last_30d"],
                "is_churn_risk": int(c["is_churn_risk"]),
                "is_flagged_abuse": int(c["is_flagged_abuse"]),
                "contacts_in_window": 0,
            }
            for c in customers
        ],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO payments (id, order_id, customer_id, amount_paise, method, status, failure_reason, created_at) "
        "VALUES (:id,:order_id,:customer_id,:amount_paise,:method,:status,:failure_reason,:created_at)",
        [
            {
                "id": p["id"], "order_id": p["order_id"], "customer_id": p["customer_id"],
                "amount_paise": p["amount_paise"], "method": p["method"], "status": p["status"],
                "failure_reason": p["failure_reason"], "created_at": p["created_at"],
            }
            for p in payments
        ],
    )
    return {"customers": len(customers), "payments": len(payments)}


def main() -> None:
    init_db()
    conn = connect()
    try:
        print("Seeded:", load(conn))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
