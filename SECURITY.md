# Security & threat model

SALVAGE touches money, so it is designed to be *red-teamed against its own author*.
This document is the "would you trust it in a money path" answer. It attacks the
system on purpose and shows where each attack stops.

## Trust boundary

The LLM is **untrusted input**, not a decision-maker. It can be wrong, jailbroken,
or adversarial and still cannot move money, because it only emits enum values that
a deterministic function re-validates and bounds.

## Attacks and where they die

| Attack | Defence | Proven by |
|---|---|---|
| **Prompt injection makes the model demand a 100% discount** | Model output is advisory; `policy.decide()` caps every incentive by %, absolute, and remaining budget | `test_policy_properties.py` (~20k inputs) |
| **Model invents a new play or a rupee amount** | `parse_llm_json` rejects anything off the fixed vocabulary; the model never emits amounts | `llm/base.py` |
| **Replayed webhook double-charges / double-links** | Dedup on `event_id`; outbox PK + `executions` UNIQUE key = exactly one action | `test_exactly_once.py` |
| **Forged webhook from an attacker** | HMAC-SHA256 signature verified in constant time (`webhook.verify`) | `webhook.py` |
| **Process crash mid-execution creates two links or none** | Re-entrant `execute_one`; deterministic link id + unique constraint | `test_exactly_once.py` |
| **Tampering with the audit log to hide an action** | Hash chain; any edit breaks all later hashes | `test_loop_and_audit.py::test_audit_tampering_is_detected` |
| **Promo abuse / discount farming** | `is_flagged_abuse` hard-veto; per-customer 30-day incentive cap; contact cap | `test_policy_cases.py` |
| **Runaway spend across many customers** | Campaign `incentive_budget_remaining_paise` caps aggregate spend | `policy.py` |
| **Silent model failure presented as real** | Provider stamped on every result; mock labelled; UI + audit show which ran | `llm/router.py` |

## Secrets

- Keys live only in `backend/.env` (git-ignored). `.env.example` documents them.
- No secret is ever logged, returned by an endpoint, or written to the audit log.
- Money amounts in logs/audit are ASCII (`Rs`), never a glyph that breaks a log
  pipeline (see FAILURES.md #1).

## Human-in-the-loop

Any spend over the merchant's `approval_threshold_paise`, and every `risk_block`,
is held in `awaiting_approval` — no money moves until a human approves via the
dashboard. Autonomy is bounded by construction, not by prompt instruction.

## What we deliberately did NOT delegate to the LLM

Revenue math, financial limits, authorization, payment state, and the recovery
amount. Those are deterministic or come from the payment API. The LLM does
diagnosis, interpretation, and tool selection — and nothing that touches money.
