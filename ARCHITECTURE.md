# Architecture

## The one boundary that matters

```
                    ┌──────────────────────────────────────────────┐
   payment.failed   │  LLM LAYER (reasoning)                        │
   ────────────────▶│  diagnoses root cause, proposes ONE play      │
                    │  OUTPUT: enum values only, no amounts          │
                    └───────────────────────┬──────────────────────┘
                                            │  Play + RootCause + advisory %
                                            ▼
                    ┌──────────────────────────────────────────────┐
                    │  POLICY ENGINE (deterministic, pure)          │
                    │  policy.decide() — the ONLY code that turns    │
                    │  a play into rupees. Caps, cooldowns, budgets, │
                    │  abuse/churn vetoes, approval threshold.       │
                    │  Proven by property tests over ~20k inputs.    │
                    └───────────────────────┬──────────────────────┘
                                            ▼
                       APPROVAL ─▶ OUTBOX ─▶ GATEWAY ─▶ EXECUTIONS ─▶ AUDIT
                       (human)     (once)    (test)     (UNIQUE key)   (hash chain)
```

Everything above the policy engine is *advisory*. Everything at or below it is
*deterministic*. Money only exists below the line.

## The 9 stages (salvage/agent.py)

| Stage | Module | What it does | Money? |
|---|---|---|---|
| OBSERVE | app.webhook | verify HMAC signature, dedup by event id, persist raw event | no |
| REASON | llm/router | Gemini→local→mock diagnosis; provider recorded truthfully | no |
| PLAN | llm/* | model proposes one play from the fixed menu | no |
| **POLICY** | **policy.decide** | **pure function converts play → bounded rupees, or vetoes** | **decides** |
| CONTROL | agent | deterministic 20% holdout for lift measurement | no |
| APPROVAL | agent | spend over threshold / risk → awaits merchant | gates |
| EXECUTE | outbox | enqueue; worker performs the single gateway call | yes (once) |
| VERIFY | outbox | link state comes from the gateway, not our optimism | reads |
| AUDIT | audit | every stage appended to the hash chain | records |
| RECOVER | outbox | retries, exactly-once on crash, dead-letter after N | safe |

## Exactly-once execution (salvage/outbox.py)

An `outbox` row (PK = recovery id) means "one money action intended." The worker
is the only performer. `execute_one` is re-entrant:

1. If an `executions` row already exists for the key → mark done, **no new call**.
   (Covers a crash *after* recording.)
2. Else call the gateway once, then `INSERT OR IGNORE` into `executions`
   (`UNIQUE(idempotency_key)`). The mock gateway derives its link id from the key,
   so a retried call returns the *same* id and the unique constraint collapses
   duplicates. (Covers a crash *before* recording.)

Either path ⇒ exactly one link. Proven in `tests/test_exactly_once.py`.

## Hash-chained audit (salvage/audit.py)

`this_hash = sha256(prev_hash + canonical_json(detail))`, genesis = 64 zeros.
Altering, deleting, or reordering any past row breaks every subsequent hash;
`verify_chain()` recomputes and reports the first break. `GET /audit/verify`
exposes it; `tests/test_loop_and_audit.py` proves tamper detection.

## AI provider abstraction (salvage/llm/)

`Router` tries Gemini → local → mock, returning the `Diagnosis` stamped with the
provider that *actually* ran. `parse_llm_json` rejects any output not in the fixed
vocabulary, so a model can never invent a cause, a play, or an amount. The mock is
rule-based and deterministic — the demo is identical with no network.

## Storage (salvage/db.py)

SQLite (WAL) for a reliable offline demo — no server, no network, byte-identical
every run. The schema is plain SQL that ports to Postgres/Supabase (see ROADMAP).
Tables: `events, customers, payments, recoveries, outbox, executions, audit`.

## Data flow, end to end

`webhook / demo driver → agent.process_failed_payment → (router, policy, control,
audit, outbox.enqueue) → outbox.run_once → gateway → executions → audit →
metrics.compute → dashboard`.
