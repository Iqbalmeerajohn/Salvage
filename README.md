# SALVAGE — AI Revenue Recovery Agent

**Razorpay AI Builder Buildathon 2026 · Track 03 — AI Revenue Recovery**

> Razorpay's existing recovery sends everyone a retry link. **SALVAGE decides who
> deserves one, prices the nudge, and proves — against a real control group —
> that it made incremental money instead of discounting people who'd have paid
> anyway.** An LLM diagnoses and proposes; a deterministic policy engine owns
> every rupee; every action is idempotent, bounded, human-approvable, and written
> to a hash-chained audit log.

Runs **fully offline, ₹0**, no accounts required. Add free API keys to upgrade
individual layers to live — with zero code changes.

---

## Why this exists

When a payment fails, Razorpay already ships **Failed Payment Recovery** (blasts a
retry link) and **Optimizer** (ML rail routing). SALVAGE owns the layer *above*
them — the decision nobody owns:

> Should **this** customer be contacted at all, with what intervention, at what
> cost, and when do we stop?

A blanket blast can't refuse. SALVAGE can — and that refusal is the product.

## The load-bearing idea

**The LLM emits enum values only. One pure, unit-tested function decides every rupee.**

```
payment.failed  ─▶ OBSERVE ─▶ REASON ─▶ PLAN ─▶ [ POLICY GATE ] ─▶ APPROVAL ─▶ EXECUTE ─▶ VERIFY ─▶ AUDIT ─▶ RECOVER
                   verify+     LLM        LLM      PURE FUNCTION      human if     idempotent   from      hash      outbox,
                   dedup       cause      play     owns the money     over cap     test-mode    gateway   chain     exactly-once
```

No matter how the model misbehaves, it cannot move more money than the merchant's
caps allow. That boundary is proven by ~20,000 randomized property-test inputs.

## Maps 1:1 to Razorpay's judging criteria

| Their criterion | Where it lives in this repo |
|---|---|
| **Problem taste** | The decision-layer thesis above; the refusal case |
| **Build quality** — "would you trust it" | `policy.py` + property tests, hash-chained `audit.py`, exactly-once `outbox.py` |
| **AI judgment** — "where you chose NOT to use one" | The pure policy engine: the LLM is structurally kept away from money |
| **Failure recovery** — "what broke" | [FAILURES.md](FAILURES.md) — a real, live log of what broke and how it got fixed |

---

## Quickstart (₹0, offline)

**Prereqs:** Python 3.11+, Node 18+.

### 1. Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_data.py          # write synthetic dataset
python -m salvage.seed                    # load it into SQLite
uvicorn salvage.app:app --port 8000       # API at http://localhost:8000
```

### 2. Frontend (in a second terminal)
```bash
cd frontend
npm install
npm run dev                               # dashboard at http://localhost:3000
```

Open **http://localhost:3000** and click **Run recovery batch**.

> **Note on this dev machine:** the repo lives on an exFAT external drive, which
> has no symlink support, so `next build` (production) fails here with `EISDIR`.
> `npm run dev` works fine. On any NTFS/Linux machine `next build` succeeds
> normally. See [FAILURES.md](FAILURES.md) #3.

## Run the tests (the proof)
```bash
cd backend
python -m pytest            # 27 tests: property, exactly-once, audit, loop
```
What they prove:
- **~20,000 randomized inputs** can't make the policy engine exceed any cap.
- **Process death mid-execution yields exactly one payment link** (never zero, never two).
- **Tampering with any past audit row is detected** by the hash chain.
- The three hero cases (refuse / recover / switch-rail) decide correctly.

## Upgrade to live (optional, still free)

Copy `backend/.env.example` → `backend/.env` and add keys as you get them:
- **Gemini** (Google AI Studio) → diagnosis switches from mock to a real model.
- **Razorpay Test Mode** → recovery links become real test-mode Payment Links.
- **Webhook secret** + `REQUIRE_WEBHOOK_SIGNATURE=true` → HMAC verification enforced.

The provider/gateway is chosen automatically from config. The UI always shows
which mode is live, and the audit log never claims a mock result was a real model.

---

## Project structure

```
backend/
  salvage/
    enums.py        fixed vocabulary the LLM may emit
    policy.py       ⭐ pure function — owns every rupee
    agent.py        the 9-stage loop orchestrator
    outbox.py       exactly-once execution worker
    audit.py        hash-chained audit log
    webhook.py      Razorpay HMAC signature verification
    llm/            Gemini -> local -> deterministic mock (never lies)
    payments/       mock gateway | real Razorpay test-mode gateway
    synth.py        synthetic dataset generator (labelled synthetic)
    outcomes.py     SIMULATED outcome model (clearly labelled)
    metrics.py      incremental-lift computation
    app.py          FastAPI: webhook + dashboard API
  tests/            property / exactly-once / audit / loop
frontend/           Next.js dashboard
data/               generated synthetic data + SQLite db
PLAN.md             the execution plan
ARCHITECTURE.md     component + data-flow detail
SECURITY.md         threat model (red-teaming our own money path)
ROADMAP.md          what v0.2+ looks like (real-merchant pilot)
FAILURES.md         what broke, and how we got out
```

## Honesty notes (stated before a judge finds them)

- **Outcomes are simulated.** The 20% holdout is a *real* split in the decision
  loop, but whether a customer actually pays is modelled by `outcomes.py` (fully
  visible, seeded). The dashboard banners this. Real conversion data is v0.2.
- **Single merchant, hand-written response model.** By design for a bounded build.
- **No load testing above ~50 rps.** Stated, not hidden.

Each limitation has a plan in [ROADMAP.md](ROADMAP.md).
