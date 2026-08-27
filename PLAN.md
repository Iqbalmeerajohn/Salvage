# SALVAGE — Execution Plan

**Track 03 — AI Revenue Recovery · Razorpay AI Builder Buildathon 2026**
Submission date: **5 September**. Budget: **₹0** (free tiers only).

---

## 1. What it is

SALVAGE is an autonomous failed-payment **recovery decision agent**. Razorpay already ships
"Failed Payment Recovery" (blasts a retry link) and Optimizer (ML rail routing). Salvage owns
the layer *above* them — the decision nobody owns:

> Should **this** customer be contacted at all, with what intervention, at what cost, and when do we stop?

An LLM **diagnoses and proposes** (enum values only). A **deterministic policy engine** — never
the model — converts every proposal into rupees, or refuses. Every action is idempotent, bounded,
human-approvable above a threshold, and written to a hash-chained audit log.

**Pitch:** *Razorpay's existing recovery sends everyone a link. Salvage decides who deserves one,
prices the nudge, and proves — with a control group — that it made incremental money instead of
discounting people who'd have paid anyway.*

## 2. Why it wins

1. Not a rebuild of their shipped product — it's the decision layer above it.
2. Answers the hiring question ("will you hurt me in a money path?") via deterministic money +
   bounded autonomy + audit chain, matching their pre-IPO governance posture.
3. Carries **evidence** — a 20% holdout control measuring *incremental* lift. Almost no applicant does this.

## 3. The 9-stage loop

```
payment.failed webhook
  OBSERVE   verify signature, dedupe by event id, persist raw event
  REASON    LLM diagnoses root cause  (enum)
  PLAN      LLM selects a play from a FIXED menu  (enum only)
  POLICY    PURE FUNCTION converts play -> rupees; caps, cooldowns, budgets, abuse/churn veto
  APPROVAL  if cost > threshold OR risk flag -> hold for merchant approval
  EXECUTE   idempotent Razorpay test-mode call; idempotency key = event id
  VERIFY    confirm state from Razorpay API, never from our own optimism
  AUDIT     append hash-chained record (prev_hash + row -> this_hash)
  RECOVER   outbox + worker retries; process-death yields EXACTLY ONE link
```

**Load-bearing boundary:** the LLM emits **enum values only**. One pure, unit-tested function
decides every rupee.

## 4. Stack (all ₹0)

| Layer | Choice |
|---|---|
| Agent/API | Python + FastAPI |
| Worker | Postgres outbox + async worker loop (no n8n in money path) |
| DB | Supabase Free (Postgres) |
| LLM | Gemini free tier -> local model -> deterministic mock (never lies about which ran) |
| Dashboard | Next.js + TypeScript on Vercel Hobby |
| Payments | Razorpay Test Mode (Orders+Checkout for volume; Payment Links for hero cases) |
| Tunnel | cloudflared / ngrok free (dev webhooks) |

## 5. LLM must NEVER

Calculate revenue · set/exceed a financial limit · authorize an action · report payment state.
Those are deterministic or come from the payment API. The LLM reasons, interprets, recommends,
and picks a tool from a fixed menu.

## 6. Locked decisions (from user)

- **Fully synthetic** dataset, clearly labelled. **No real-merchant claim anywhere** (no "Vizag SMB"
  story — it is not true and must never appear in submission/resume). Real-merchant pilot lives only
  in ROADMAP.md as future work.
- Demo surface: **Next.js dashboard** (approval UI + audit viewer + incremental-lift metrics).
- Agentic-commerce stretch: **only after core is green**.
- Build mode: **phase by phase, check in at each gate**.

## 7. Phases & gates

- **Phase 0 — Core (offline, no accounts).** Repo scaffold · pure policy engine · property tests ·
  synthetic dataset generator · deterministic mock LLM.
  **Gate:** property tests prove no policy output can exceed any cap for *any* input. ← building now
- **Phase 1 — Spine.** FastAPI webhook (signature verify + dedupe) · outbox + worker · Razorpay
  test-mode link creation, idempotent. **Gate:** one real `payment.failed` -> one verified link, once.
- **Phase 2 — Intelligence.** Gemini diagnosis + play selection behind provider abstraction with
  local + mock fallback. Refusal case (churn-risk, 2 incentives/30d -> DO_NOTHING) demoable.
- **Phase 3 — Evidence.** Dashboard · 20% holdout control · incremental-lift metrics · audit viewer.
- **Phase 4 — Proof of trust.** Threat model · webhook-replay test · the two paranoid property tests ·
  ROADMAP.md. **This is the "show I can be trusted near money" security deliverable.**
- **Phase 5 — Submission.** README · ARCHITECTURE.md + diagram · 5-min video · deploy · demo dry-runs.
  Freeze ~3 Sept, submit ~4 Sept.

## 8. Accounts to create (user does these — all free, no card)

- [ ] Razorpay **Test Mode** account -> Key ID, Key Secret, Webhook Secret
- [ ] Supabase free project -> Postgres connection string
- [ ] Google AI Studio -> Gemini API key
- [ ] Vercel Hobby (deploy dashboard) — later
- [ ] GitHub repo — later

## 9. Definition of done

Threat model · hash-chained audit · property + failure tests · holdout control with real numbers ·
ARCHITECTURE.md + diagram · ROADMAP.md · demo mode + test mode documented · repeatable 5-min demo.
