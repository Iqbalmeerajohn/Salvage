"""Provider router: fallback behaviour and strict enum validation."""
from __future__ import annotations

import pytest

from salvage.enums import Play, RootCause
from salvage.llm.base import Diagnosis, parse_llm_json
from salvage.llm.mock import MockProvider
from salvage.llm.router import Router


class _Failing:
    name = "flaky"

    def available(self):
        return True

    def diagnose(self, features):
        raise RuntimeError("boom")


def test_router_falls_through_to_mock_and_records_the_failure():
    r = Router(providers=[_Failing(), MockProvider()])
    d, notes = r.diagnose({"failure_reason": "otp_drop"})
    assert d.provider == "mock"
    assert any("flaky failed" in n for n in notes)


def test_router_uses_first_available():
    d, notes = Router(providers=[MockProvider()]).diagnose({"failure_reason": "bank_downtime"})
    assert d.provider == "mock"
    assert d.proposed_play == Play.SWITCH_RAIL
    assert notes == []


def test_parse_rejects_invalid_play():
    with pytest.raises(ValueError):
        parse_llm_json(
            {"root_cause": "otp_drop", "proposed_play": "give_free_money", "proposed_incentive_pct": 5},
            provider="gemini", model_name="x",
        )


def test_parse_rejects_invalid_root_cause():
    with pytest.raises(ValueError):
        parse_llm_json(
            {"root_cause": "aliens", "proposed_play": "do_nothing", "proposed_incentive_pct": 0},
            provider="gemini", model_name="x",
        )


def test_parse_clamps_incentive_pct():
    d = parse_llm_json(
        {"root_cause": "otp_drop", "proposed_play": "small_incentive", "proposed_incentive_pct": 999},
        provider="gemini", model_name="x",
    )
    assert 0 <= d.proposed_incentive_pct <= 100
    assert isinstance(d, Diagnosis) and d.root_cause == RootCause.OTP_DROP
