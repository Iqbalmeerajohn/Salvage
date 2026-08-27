"""Deterministic mock provider — the emergency fallback that always works.

It is rule-based, not random, so the demo is identical every run even with no
internet and no API key. Crucially it stamps itself `provider="mock"`, so the
UI and audit trail always show that a real model did NOT run. Honesty about
provenance is a feature, not a limitation.
"""
from __future__ import annotations

from ..enums import Play, RootCause
from .base import Diagnosis

# A sensible default play per root cause. This is the same reasoning a language
# model would produce for these well-understood cases — encoded as rules.
_PLAY_BY_CAUSE = {
    RootCause.INSUFFICIENT_FUNDS: (Play.SMALL_INCENTIVE, 8),
    RootCause.OTP_DROP: (Play.SMALL_INCENTIVE, 5),
    RootCause.BANK_DOWNTIME: (Play.SWITCH_RAIL, 0),
    RootCause.RISK_BLOCK: (Play.DO_NOTHING, 0),
    RootCause.EXPIRED_INSTRUMENT: (Play.NUDGE_NO_INCENTIVE, 0),
    RootCause.UNKNOWN: (Play.RETRY_SAME_RAIL, 0),
}


class MockProvider:
    name = "mock"

    def available(self) -> bool:
        return True  # always

    def diagnose(self, features: dict) -> Diagnosis:
        cause = RootCause(features.get("failure_reason") or RootCause.UNKNOWN.value)
        play, pct = _PLAY_BY_CAUSE[cause]
        return Diagnosis(
            root_cause=cause,
            proposed_play=play,
            proposed_incentive_pct=pct,
            rationale=f"[deterministic rules] {cause.value} -> {play.value}",
            provider="mock",
            model_name="rule-based-v1",
        )
