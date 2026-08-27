"""Fixed vocabularies for the SALVAGE recovery agent.

The LLM is only ever allowed to emit values from these enums. It never emits
free-form amounts, SQL, or instructions. Everything downstream of the model
speaks in these terms, which is what lets a pure function own every rupee.
"""
from __future__ import annotations

from enum import Enum


class RootCause(str, Enum):
    """Why a payment failed. The LLM classifies into exactly one of these."""

    INSUFFICIENT_FUNDS = "insufficient_funds"
    OTP_DROP = "otp_drop"            # customer abandoned at the OTP / auth step
    BANK_DOWNTIME = "bank_downtime"  # issuer / rail temporarily down
    RISK_BLOCK = "risk_block"        # blocked by fraud / risk rules
    EXPIRED_INSTRUMENT = "expired_instrument"
    UNKNOWN = "unknown"


class Play(str, Enum):
    """The fixed menu of interventions. The LLM proposes one; the policy
    engine may downgrade or veto it, but can never invent a new one."""

    RETRY_SAME_RAIL = "retry_same_rail"        # nudge to retry, no rail change, no money
    SWITCH_RAIL = "switch_rail"                # suggest a different method, no money
    NUDGE_NO_INCENTIVE = "nudge_no_incentive"  # reminder only, no money
    SMALL_INCENTIVE = "small_incentive"        # the only play that spends money
    DO_NOTHING = "do_nothing"                  # explicit, audited non-action


# Plays that are structurally incapable of costing money. The policy engine
# guarantees incentive == 0 for every one of these, for every input.
ZERO_COST_PLAYS = frozenset(
    {
        Play.RETRY_SAME_RAIL,
        Play.SWITCH_RAIL,
        Play.NUDGE_NO_INCENTIVE,
        Play.DO_NOTHING,
    }
)
