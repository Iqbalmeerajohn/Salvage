"""Named example tests — the human-readable behaviours, including the on-camera
'refusal' demo case. Property tests prove safety over all inputs; these prove
the specific stories we tell a judge are actually true.
"""
from __future__ import annotations

from salvage.enums import Play, RootCause
from salvage.policy import (
    CustomerState,
    MerchantPolicy,
    RecoveryContext,
    decide,
)

POLICY = MerchantPolicy(
    max_incentive_pct=10,
    max_incentive_paise=20_000,
    incentive_budget_remaining_paise=500_000,
    max_contacts_per_window=2,
    incentives_per_30d_cap=2,
    approval_threshold_paise=10_000,
)


def _good_customer(**kw):
    base = dict(
        lifetime_value_paise=1_500_000,
        orders_count=6,
        days_since_last_order=12,
        incentives_last_30d=0,
        is_churn_risk=False,
        is_flagged_abuse=False,
        contacts_in_window=0,
    )
    base.update(kw)
    return CustomerState(**base)


def test_the_refusal_case():
    """THE demo beat: churn-risk customer, 2 incentives in 30 days, hard decline.
    Razorpay's blanket recovery would send a link. Salvage refuses."""
    customer = _good_customer(is_churn_risk=True, incentives_last_30d=2)
    ctx = RecoveryContext(
        amount_paise=340_000,
        root_cause=RootCause.INSUFFICIENT_FUNDS,
        proposed_play=Play.SMALL_INCENTIVE,
        proposed_incentive_pct=10,
    )
    d = decide(customer, POLICY, ctx)
    assert d.final_play == Play.DO_NOTHING
    assert d.incentive_paise == 0
    assert d.vetoed is True


def test_healthy_customer_gets_a_capped_incentive():
    customer = _good_customer()
    ctx = RecoveryContext(
        amount_paise=340_000,           # ₹3,400
        root_cause=RootCause.OTP_DROP,
        proposed_play=Play.SMALL_INCENTIVE,
        proposed_incentive_pct=10,
    )
    d = decide(customer, POLICY, ctx)
    assert d.final_play == Play.SMALL_INCENTIVE
    # 10% of ₹3,400 = ₹340 = 34,000 paise, but absolute cap is ₹200 = 20,000 paise.
    assert d.incentive_paise == 20_000
    assert d.requires_approval is True  # 20,000 > 10,000 threshold


def test_bank_downtime_forces_switch_rail_no_money():
    customer = _good_customer()
    ctx = RecoveryContext(
        amount_paise=340_000,
        root_cause=RootCause.BANK_DOWNTIME,
        proposed_play=Play.SMALL_INCENTIVE,  # LLM wrongly wants to spend
        proposed_incentive_pct=10,
    )
    d = decide(customer, POLICY, ctx)
    assert d.final_play == Play.SWITCH_RAIL
    assert d.incentive_paise == 0
    assert d.vetoed is True


def test_abuse_flag_hard_stops():
    customer = _good_customer(is_flagged_abuse=True)
    ctx = RecoveryContext(
        amount_paise=340_000,
        root_cause=RootCause.INSUFFICIENT_FUNDS,
        proposed_play=Play.SMALL_INCENTIVE,
        proposed_incentive_pct=10,
    )
    d = decide(customer, POLICY, ctx)
    assert d.final_play == Play.DO_NOTHING
    assert d.incentive_paise == 0


def test_discount_fatigue_downgrades_non_churn_to_nudge():
    customer = _good_customer(incentives_last_30d=2, is_churn_risk=False)
    ctx = RecoveryContext(
        amount_paise=340_000,
        root_cause=RootCause.OTP_DROP,
        proposed_play=Play.SMALL_INCENTIVE,
        proposed_incentive_pct=10,
    )
    d = decide(customer, POLICY, ctx)
    assert d.final_play == Play.NUDGE_NO_INCENTIVE
    assert d.incentive_paise == 0


def test_exhausted_budget_degrades_to_nudge():
    customer = _good_customer()
    policy = MerchantPolicy(
        max_incentive_pct=10,
        max_incentive_paise=20_000,
        incentive_budget_remaining_paise=0,   # nothing left
        approval_threshold_paise=10_000,
    )
    ctx = RecoveryContext(
        amount_paise=340_000,
        root_cause=RootCause.OTP_DROP,
        proposed_play=Play.SMALL_INCENTIVE,
        proposed_incentive_pct=10,
    )
    d = decide(customer, policy, ctx)
    assert d.final_play == Play.NUDGE_NO_INCENTIVE
    assert d.incentive_paise == 0


def test_contact_cap_stays_silent():
    customer = _good_customer(contacts_in_window=2)
    ctx = RecoveryContext(
        amount_paise=340_000,
        root_cause=RootCause.OTP_DROP,
        proposed_play=Play.NUDGE_NO_INCENTIVE,
        proposed_incentive_pct=0,
    )
    d = decide(customer, POLICY, ctx)
    assert d.final_play == Play.DO_NOTHING
