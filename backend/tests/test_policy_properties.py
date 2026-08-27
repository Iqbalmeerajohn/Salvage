"""Property tests for the policy engine.

These are the tests that make a payments panel trust the money path. Instead of
checking a handful of examples, Hypothesis throws thousands of random, adversarial
inputs at `decide()` and asserts the safety invariants hold for ALL of them.

If any of these ever fail, the boundary that keeps the LLM away from money is broken.
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from salvage.enums import ZERO_COST_PLAYS, Play, RootCause
from salvage.policy import (
    CustomerState,
    MerchantPolicy,
    RecoveryContext,
    decide,
)

# ---- Strategies: generate every plausible (and implausible) input. ----------

customers = st.builds(
    CustomerState,
    lifetime_value_paise=st.integers(min_value=0, max_value=10_000_000),
    orders_count=st.integers(min_value=0, max_value=500),
    days_since_last_order=st.integers(min_value=0, max_value=2000),
    incentives_last_30d=st.integers(min_value=0, max_value=50),
    is_churn_risk=st.booleans(),
    is_flagged_abuse=st.booleans(),
    contacts_in_window=st.integers(min_value=0, max_value=50),
)

policies = st.builds(
    MerchantPolicy,
    max_incentive_pct=st.integers(min_value=0, max_value=100),
    max_incentive_paise=st.integers(min_value=0, max_value=1_000_000),
    incentive_budget_remaining_paise=st.integers(min_value=-100, max_value=5_000_000),
    max_contacts_per_window=st.integers(min_value=0, max_value=10),
    incentives_per_30d_cap=st.integers(min_value=0, max_value=10),
    approval_threshold_paise=st.integers(min_value=0, max_value=1_000_000),
)

contexts = st.builds(
    RecoveryContext,
    amount_paise=st.integers(min_value=1, max_value=100_000_000),
    root_cause=st.sampled_from(list(RootCause)),
    proposed_play=st.sampled_from(list(Play)),
    proposed_incentive_pct=st.integers(min_value=-50, max_value=500),  # includes bad input
)


@settings(max_examples=2000)
@given(customers, policies, contexts)
def test_incentive_is_never_negative(customer, policy, ctx):
    d = decide(customer, policy, ctx)
    assert d.incentive_paise >= 0


@settings(max_examples=2000)
@given(customers, policies, contexts)
def test_incentive_never_exceeds_absolute_cap(customer, policy, ctx):
    d = decide(customer, policy, ctx)
    assert d.incentive_paise <= policy.max_incentive_paise


@settings(max_examples=2000)
@given(customers, policies, contexts)
def test_incentive_never_exceeds_percentage_cap(customer, policy, ctx):
    d = decide(customer, policy, ctx)
    max_by_pct = (ctx.amount_paise * policy.max_incentive_pct) // 100
    assert d.incentive_paise <= max_by_pct


@settings(max_examples=2000)
@given(customers, policies, contexts)
def test_incentive_never_exceeds_remaining_budget(customer, policy, ctx):
    d = decide(customer, policy, ctx)
    assert d.incentive_paise <= max(0, policy.incentive_budget_remaining_paise)


@settings(max_examples=2000)
@given(customers, policies, contexts)
def test_zero_cost_plays_carry_zero_money(customer, policy, ctx):
    d = decide(customer, policy, ctx)
    if d.final_play in ZERO_COST_PLAYS:
        assert d.incentive_paise == 0


@settings(max_examples=2000)
@given(customers, policies, contexts)
def test_only_small_incentive_can_spend(customer, policy, ctx):
    d = decide(customer, policy, ctx)
    if d.incentive_paise > 0:
        assert d.final_play == Play.SMALL_INCENTIVE


@settings(max_examples=2000)
@given(customers, policies, contexts)
def test_abuse_is_always_refused(customer, policy, ctx):
    d = decide(customer, policy, ctx)
    if customer.is_flagged_abuse:
        assert d.final_play == Play.DO_NOTHING
        assert d.incentive_paise == 0


@settings(max_examples=2000)
@given(customers, policies, contexts)
def test_spend_above_threshold_requires_approval(customer, policy, ctx):
    d = decide(customer, policy, ctx)
    if d.incentive_paise > policy.approval_threshold_paise:
        assert d.requires_approval is True


@settings(max_examples=2000)
@given(customers, policies, contexts)
def test_final_play_is_always_from_the_fixed_menu(customer, policy, ctx):
    d = decide(customer, policy, ctx)
    assert d.final_play in set(Play)


@settings(max_examples=2000)
@given(customers, policies, contexts)
def test_output_is_deterministic(customer, policy, ctx):
    # Same input, same decision — no hidden clock or randomness.
    assert decide(customer, policy, ctx) == decide(customer, policy, ctx)
