"""SIMULATED outcome model — clearly labelled, never presented as real data.

The honest limitation of a hackathon build with no live merchant: we cannot
observe whether a customer actually paid after an intervention. Rather than
hide that, we make it explicit. This module is a documented, seeded model that
estimates recovery outcomes so the dashboard can show an *incremental lift*
number — with a visible banner that these are modelled, not measured.

Parameters are here in the open so a judge can see exactly what we assumed.
The 20% control group is real (a true holdout in the decision loop); only the
per-customer pay/no-pay outcome is modelled.
"""
from __future__ import annotations

import hashlib

from .enums import Play, RootCause

# Base probability a failed payment is recovered organically (no intervention),
# by root cause. Bank downtime mostly self-resolves; risk blocks rarely recover.
ORGANIC_RECOVERY = {
    RootCause.INSUFFICIENT_FUNDS.value: 0.12,
    RootCause.OTP_DROP.value: 0.30,
    RootCause.BANK_DOWNTIME.value: 0.45,
    RootCause.RISK_BLOCK.value: 0.03,
    RootCause.EXPIRED_INSTRUMENT.value: 0.08,
    RootCause.UNKNOWN.value: 0.10,
}

# Additive uplift from each play (capped at 0.95 total).
PLAY_UPLIFT = {
    Play.SMALL_INCENTIVE.value: 0.22,
    Play.NUDGE_NO_INCENTIVE.value: 0.10,
    Play.SWITCH_RAIL.value: 0.15,
    Play.RETRY_SAME_RAIL.value: 0.08,
    Play.DO_NOTHING.value: 0.0,
}

MODEL_LABEL = "SIMULATED — outcomes modelled by salvage/outcomes.py, not measured on real customers"


def recovery_probability(root_cause: str, play: str, treated: bool) -> float:
    base = ORGANIC_RECOVERY.get(root_cause, 0.10)
    if not treated:
        return base
    return min(0.95, base + PLAY_UPLIFT.get(play, 0.0))


def is_recovered(recovery_id: str, root_cause: str, play: str, treated: bool) -> bool:
    """Deterministic Bernoulli draw seeded by the recovery id, so results are
    stable across runs (same demo every time)."""
    p = recovery_probability(root_cause, play, treated)
    draw = int(hashlib.sha256(("outcome:" + recovery_id).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return draw < p
