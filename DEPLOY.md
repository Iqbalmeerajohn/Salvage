# Deploying SALVAGE to the cloud (free, always-reachable)

The database is **already created and seeded** (Supabase project `salvage`, Mumbai).
What's left is connecting the two Vercel projects and pasting a few values — the
parts that need your logged-in dashboard (secrets + GitHub authorization) and
can't be done headlessly.

Target: **Vercel (frontend + backend serverless) + Supabase Postgres.**
Runs 24/7, laptop off, ₹0.

---

## 0. One-time: let Vercel see the repo

github.com/apps/vercel → **Configure** → your account → under *Repository access*
add **Iqbalmeerajohn/Salvage** (or "All repositories"). This is why the automated
link failed — Vercel could see your other repos but not this new one.

## 1. Backend → Vercel (project: salvage-api)

Vercel → **Add New → Project** → import **Iqbalmeerajohn/Salvage**.

- **Root Directory:** `backend`
- Framework preset: **Other** (the included `vercel.json` handles routing)
- **Environment Variables** (Settings → Environment Variables):

  | Name | Value |
  |---|---|
  | `DATABASE_URL` | `postgresql://postgres:YOUR_DB_PASSWORD@db.csrbzzjaeaxayxkoteyr.supabase.co:5432/postgres?sslmode=require` |
  | `GEMINI_API_KEY` | your Gemini key (the one already in `backend/.env`) |
  | `GEMINI_MODEL` | `gemini-3.5-flash` |

  Get `YOUR_DB_PASSWORD` at: Supabase → project **salvage** → Settings → Database →
  *Connection string* → reveal/reset password.

- Deploy. Note the URL, e.g. `https://salvage-api.vercel.app`.
- Verify: open `https://salvage-api.vercel.app/health` → should show
  `"gateway":"mock","llm":"gemini"`. Then POST `/demo/run-batch` (or just let the
  dashboard do it) — the app seeds Postgres itself on first call.

## 2. Frontend → Vercel (project: salvage-dashboard)

Vercel → **Add New → Project** → import the same repo again.

- **Root Directory:** `frontend`
- Framework preset: **Next.js** (auto-detected)
- **Environment Variable:**

  | Name | Value |
  |---|---|
  | `NEXT_PUBLIC_API_URL` | your backend URL from step 1, e.g. `https://salvage-api.vercel.app` |

- Deploy. This is your public dashboard URL — put it in the buildathon form.

## 3. Done

Every `git push` now auto-deploys both. To go fully live on payments later, add
`RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / `RAZORPAY_WEBHOOK_SECRET` to the
backend project and set `REQUIRE_WEBHOOK_SIGNATURE=true`.

---

## Alternative: Render (if you want a true always-on background worker)

`render.yaml` in the repo root is a one-click Blueprint (Render → New → Blueprint →
select repo). It provisions its **own** free Postgres, wires `DATABASE_URL`
automatically, runs a continuous worker (`RUN_WORKER=true`), and only asks you to
paste `GEMINI_API_KEY`. Trade-off: Render free web services cold-start slower than
Vercel. If you use this, you don't need the Supabase step — pick one DB, not both.

## Notes

- **Supabase already has:** the full schema + 62 customers seeded. Payments seed
  themselves on the backend's first request (deterministic synth).
- The `salvage` Supabase project and any leftover empty Vercel projects can be
  deleted from their dashboards if you switch approaches — nothing else depends on them.
