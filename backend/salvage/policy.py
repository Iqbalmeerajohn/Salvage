"""The deterministic policy engine — the load-bearing boundary of SALVAGE.

This module is a PURE FUNCTION: no I/O, no randomness, no clock, no network,
no LLM. Given the same inputs it always returns the same decision. It is the
only place in the system that converts a proposed play into rupees, and it is
structurally incapable of exceeding any configured cap.

Everything the LLM produces enters here as an enum + a *requested* percentage,
and leaves here as a bounded, auditable decision. If this function is correct,
no amount of LLM misbehaviour can move more money than the merchant allowed.

Amounts are integer paise everywhere. We never use floats for money.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .enums import ZERO_COST_PLAYS, Play, RootCause


@dataclass(frozen=True)
class CustomerState:
    """What we know about the customer whose payment failed."""

    lifetime_value_paise: int          # total paid historically
    orders_count: int                  # successful orders to date
    days_since_last_order: int
    incentives_last_30d: int           # discounts already given in the last 30 days
    is_churn_risk: bool = False        # model/heuristic flag
    is_flagged_abuse: bool = False     # hard block: promo abuse / chargeback history
    contacts_in_window: int = 0        # recovery contacts already sent this window


@dataclass(frozen=True)
class MerchantPolicy:
    """Caps the merchant sets. The engine can spend up to, never beyond, these."""

    max_incentive_pct: int = 10               # percent of order value, integer
    max_incentive_paise: int = 20_000         # absolute per-intervention ceiling (₹200)
    incentive_budget_remaining_paise: int = 500_000  # what's left in the campaign budget
    max_contacts_per_window: int = 2          # anti-spam
    incentives_per_30d_cap: int = 2           # per-customer discount fatigue cap
    approval_threshold_paise: int = 10_000    # spend above this needs a human (₹100)


@dataclass(frozen=True)
class RecoveryContext:
    """The failed payment plus the model's proposal."""

    amount_paise: int
    root_cause: RootCause
    proposed_play: Play
    proposed_incentive_pct: int = 0    # what the LLM *asked* for; advisory only


@dataclass(frozen=True)
class PolicyDecision:
    final_play: Play
    incentive_paise: int
    requires_approval: bool
    vetoed: bool                       # True if the engine overrode the LLM's play
    reasons: tuple[str, ...] = field(default_factory=tuple)


def decide(
    customer: CustomerState,
    policy: MerchantPolicy,
    ctx: RecoveryContext,
) -> PolicyDecision:
    """Convert a proposed play into a bounded, auditable decision.

    Invariants guaranteed for EVERY possible input (see property tests):
      1. incentive_paise >= 0
      2. incentive_paise <= policy.max_incentive_paise
      3. incentive_paise <= policy.max_incentive_pct% of amount
      4. incentive_paise <= policy.incentive_budget_remaining_paise
      5. final_play in ZERO_COST_PLAYS  =>  incentive_paise == 0
      6. requires_approval is True whenever a risk flag is present or spend
         exceeds the approval threshold
    """
    reasons: list[str] = []

    # --- Hard vetoes: these override the LLM completely. ---------------------
    if customer.is_flagged_abuse:
        return PolicyDecision(
            final_play=Play.DO_NOTHING,
            incentive_paise=0,
            requires_approval=False,
            vetoed=True,
            reasons=("customer flagged for abuse; no intervention",),
        )

    if customer.contacts_in_window >= policy.max_contacts_per_window:
        return PolicyDecision(
            final_play=Play.DO_NOTHING,
            incentive_paise=0,
            requires_approval=False,
            vetoed=True,
            reasons=("contact cap reached for this window; staying silent",),
        )

    # A down bank cannot be fixed by a discount. Deterministically switch rail.
    if ctx.root_cause == RootCause.BANK_DOWNTIME:
        vetoed = ctx.proposed_play != Play.SWITCH_RAIL
        if vetoed:
            reasons.append("bank downtime: forced SWITCH_RAIL, money can't fix an outage")
        return PolicyDecision(
            final_play=Play.SWITCH_RAIL,
            incentive_paise=0,
            requires_approval=False,
            vetoed=vetoed,
            reasons=tuple(reasons),
        )

    # A risk-blocked payment must never be greased with an incentive.
    if ctx.root_cause == RootCause.RISK_BLOCK:
        vetoed = ctx.proposed_play == Play.SMALL_INCENTIVE
        if vetoed:
            reasons.append("risk block: incentive refused, escalating for review")
        return PolicyDecision(
            final_play=Play.DO_NOTHING,
            incentive_paise=0,
            requires_approval=True,  # a human should see risk blocks
            vetoed=vetoed,
            reasons=tuple(reasons) or ("risk block: held for human review",),
        )

    play = ctx.proposed_play

    # --- Discount-fatigue guard: the "refusal" demo case. -------------------
    # Too many recent discounts, especially for a churn-risk customer, means a
    # discount is training the customer to fail on purpose. Downgrade or refuse.
    if play == Play.SMALL_INCENTIVE and customer.incentives_last_30d >= policy.incentives_per_30d_cap:
        if customer.is_churn_risk:
            reasons.append(
                "churn-risk customer with %d incentives in 30d: refusing to discount"
                % customer.incentives_last_30d
            )
            return PolicyDecision(
                final_play=Play.DO_NOTHING,
                incentive_paise=0,
                requires_approval=False,
                vetoed=True,
                reasons=tuple(reasons),
            )
        reasons.append("discount fatigue: downgraded incentive to a plain nudge")
        play = Play.NUDGE_NO_INCENTIVE

    # --- Money: only SMALL_INCENTIVE can spend, and only within every cap. ---
    incentive_paise = 0
    if play == Play.SMALL_INCENTIVE:
        requested_pct = max(0, ctx.proposed_incentive_pct)
        pct = min(requested_pct, policy.max_incentive_pct)
        by_pct = (ctx.amount_paise * pct) // 100          # integer paise
        incentive_paise = min(
            by_pct,
            policy.max_incentive_paise,
            max(0, policy.incentive_budget_remaining_paise),
        )
        incentive_paise = max(0, incentive_paise)
        # If every cap crushed the incentive to zero, spending nothing is not a
        # discount — degrade honestly to a plain nudge.
        if incentive_paise == 0:
            reasons.append("no budget/headroom for an incentive: sending a plain nudge")
            play = Play.NUDGE_NO_INCENTIVE

    # Belt-and-braces: any zero-cost play carries exactly zero money.
    if play in ZERO_COST_PLAYS:
        incentive_paise = 0

    requires_approval = incentive_paise > policy.approval_threshold_paise
    if requires_approval:
        reasons.append(
            "spend Rs %.2f exceeds approval threshold Rs %.2f: awaiting merchant"
            % (incentive_paise / 100, policy.approval_threshold_paise / 100)
        )

    if not reasons:
        reasons.append("proposed play accepted within policy")

    return PolicyDecision(
        final_play=play,
        incentive_paise=incentive_paise,
        requires_approval=requires_approval,
        vetoed=play != ctx.proposed_play,
        reasons=tuple(reasons),
    )
