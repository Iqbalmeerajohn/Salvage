"""Load the synthetic dataset (data/*.json) into the SQLite database."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .db import connect, init_db

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load(conn: sqlite3.Connection, data_dir: Path = DATA_DIR) -> dict[str, int]:
    customers = json.loads((data_dir / "customers.json").read_text(encoding="utf-8"))
    payments = json.loads((data_dir / "payments.json").read_text(encoding="utf-8"))

    conn.executemany(
        "INSERT OR REPLACE INTO customers (id, name, segment, lifetime_value_paise, orders_count, "
        "days_since_last_order, incentives_last_30d, is_churn_risk, is_flagged_abuse, contacts_in_window) "
        "VALUES (:id,:name,:segment,:lifetime_value_paise,:orders_count,:days_since_last_order,"
        ":incentives_last_30d,:is_churn_risk,:is_flagged_abuse,0)",
        [
            {**c, "is_churn_risk": int(c["is_churn_risk"]), "is_flagged_abuse": int(c["is_flagged_abuse"])}
            for c in customers
        ],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO payments (id, order_id, customer_id, amount_paise, method, status, failure_reason, created_at) "
        "VALUES (:id,:order_id,:customer_id,:amount_paise,:method,:status,:failure_reason,:created_at)",
        payments,
    )
    return {"customers": len(customers), "payments": len(payments)}


def main() -> None:
    init_db()
    conn = connect()
    try:
        counts = load(conn)
        print("Seeded:", counts)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
