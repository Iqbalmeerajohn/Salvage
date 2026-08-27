"""Incremental-lift metrics computed from the recoveries table + the (labelled)
simulated outcome model. The control group is a real 20% holdout in the decision
loop; comparing its recovery rate to the treated group's is what turns "we sent
links" into "we made incremental money."
"""
from __future__ import annotations

import sqlite3

from . import outcomes


def compute(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT * FROM recoveries").fetchall()

    treated = {"n": 0, "recovered_n": 0, "recovered_value_paise": 0, "incentive_cost_paise": 0}
    control = {"n": 0, "recovered_n": 0, "recovered_value_paise": 0}
    value_at_risk = 0

    for r in rows:
        value_at_risk += r["amount_paise"]
        is_control = bool(r["in_control_group"])
        # "treated" = we actually acted (a link went out). Control + do-nothing don't.
        acted = (not is_control) and r["status"] in ("executing", "executed", "awaiting_approval")
        recovered = outcomes.is_recovered(r["id"], r["root_cause"], r["final_play"], treated=acted)

        if is_control:
            control["n"] += 1
            if recovered:
                control["recovered_n"] += 1
                control["recovered_value_paise"] += r["amount_paise"]
        else:
            treated["n"] += 1
            if acted:
                treated["incentive_cost_paise"] += r["incentive_paise"]
            if recovered:
                treated["recovered_n"] += 1
                treated["recovered_value_paise"] += max(0, r["amount_paise"] - r["incentive_paise"])

    t_rate = (treated["recovered_n"] / treated["n"]) if treated["n"] else 0.0
    c_rate = (control["recovered_n"] / control["n"]) if control["n"] else 0.0
    lift = t_rate - c_rate

    # Estimated incremental value: apply the lift to the treated population's value.
    treated_value = sum(
        r["amount_paise"] for r in rows if not r["in_control_group"]
    )
    incremental_value_paise = int(lift * treated_value)

    return {
        "label": outcomes.MODEL_LABEL,
        "value_at_risk_paise": value_at_risk,
        "treated": treated,
        "control": control,
        "treated_recovery_rate": round(t_rate, 4),
        "control_recovery_rate": round(c_rate, 4),
        "incremental_lift": round(lift, 4),
        "incremental_value_paise": incremental_value_paise,
        "net_incremental_value_paise": incremental_value_paise - treated["incentive_cost_paise"],
    }
