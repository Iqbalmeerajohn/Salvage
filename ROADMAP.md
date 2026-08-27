# Roadmap

The submission is v0.1: a complete, bounded recovery loop with proven safety.
This is what more time buys — and it changes the *evidence*, not the architecture.

## v0.1 — shipped (this submission)

- 9-stage recovery loop, LLM-diagnosis + deterministic policy engine.
- Exactly-once execution, hash-chained audit, HMAC webhook verification.
- Synthetic dataset, 20% real holdout, incremental-lift dashboard.
- Gemini / local / mock provider chain; mock + Razorpay-test gateways.
- 27 tests incl. ~20k-input property proofs and crash-safety.

## v0.2 — real evidence (the honest fix for the one weakness)

The single weakness of v0.1 is that customer *outcomes* are simulated
(`outcomes.py`, clearly labelled). The fix is not more code — it's real data:

1. Move storage SQLite → Supabase/Postgres (schema already portable).
2. Onboard a consenting merchant on Razorpay **live** mode, read-only first.
3. Point a real `payment.failed` webhook at the loop; keep the 20% holdout.
4. Run 4–6 weeks and report **measured** incremental lift with a live control —
   replacing the simulated outcome model entirely.

Result: the submission line changes from "modelled +30% lift" to "measured
₹X incremental across N real failed payments, holdout-controlled, audit-trailed."

## v0.3 — remove our own LLM from the Plan step

Once outcome data exists, a **contextual bandit** beats a language model at
choosing between five known plays — cheaper, faster, fully auditable. The LLM
stays for diagnosis and cold-start, where it is genuinely better. Proposing to
remove your own AI where a simpler mechanism wins is the senior move.

## v0.4 — agent-readable recovery surface (touches Track 1)

Expose the recovery flow so an external AI buyer-agent could complete the payment,
demonstrating agentic commerce on a loop that actually works — without depending
on protocol theatre. Strictly after the core stays green.

## Operational hardening (ongoing)

- Load testing beyond ~50 rps; backpressure on the outbox worker.
- Per-merchant policy config UI; multi-merchant isolation.
- Dead-letter review + replay tooling; alerting on policy vetoes spiking.
