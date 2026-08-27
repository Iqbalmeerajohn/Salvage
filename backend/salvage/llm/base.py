"""Shared types for the LLM layer.

The model's ONLY job is diagnosis + proposing a play from the fixed menu. It
returns enum values and an integer percentage — never a rupee amount, never a
free-form action. Every result is stamped with the provider that actually
produced it, so a mock result can never be presented as a live-model result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..enums import Play, RootCause


@dataclass(frozen=True)
class Diagnosis:
    root_cause: RootCause
    proposed_play: Play
    proposed_incentive_pct: int      # advisory; policy engine is the authority
    rationale: str
    provider: str                    # "mock" | "gemini" | "local" — the truth
    model_name: str


class LLMProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def diagnose(self, features: dict) -> Diagnosis:
        """Given a failed-payment feature dict, return a Diagnosis. Must raise on
        any failure so the router can fall through to the next provider."""
        ...


VALID_PLAYS = {p.value for p in Play}
VALID_CAUSES = {c.value for c in RootCause}


def parse_llm_json(raw: dict, provider: str, model_name: str) -> Diagnosis:
    """Validate a model's JSON against the fixed vocabulary. Anything off-menu
    raises — a model is never allowed to invent a cause, a play, or an amount."""
    cause = str(raw.get("root_cause", "")).strip().lower()
    play = str(raw.get("proposed_play", "")).strip().lower()
    if cause not in VALID_CAUSES:
        raise ValueError(f"{provider} returned invalid root_cause: {cause!r}")
    if play not in VALID_PLAYS:
        raise ValueError(f"{provider} returned invalid play: {play!r}")
    try:
        pct = int(raw.get("proposed_incentive_pct", 0))
    except (TypeError, ValueError):
        pct = 0
    pct = max(0, min(pct, 100))  # clamp; policy caps it again anyway
    rationale = str(raw.get("rationale", ""))[:500]
    return Diagnosis(
        root_cause=RootCause(cause),
        proposed_play=Play(play),
        proposed_incentive_pct=pct,
        rationale=rationale,
        provider=provider,
        model_name=model_name,
    )
