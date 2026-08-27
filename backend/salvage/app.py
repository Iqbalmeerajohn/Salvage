"""FastAPI application: webhook ingress + dashboard API.

Runs fully offline in demo mode. The webhook endpoint is real (signature verify
+ dedup); the /demo endpoints let you drive the loop from the synthetic dataset
without a live Razorpay account.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from . import agent, audit, metrics, outbox
from .config import settings
from .db import connect, init_db
from .payments.factory import get_gateway
from .seed import load

app = FastAPI(title="SALVAGE", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_ready = False


def _db():
    """Return a ready connection. Idempotently bootstraps the schema and seeds
    synthetic data on first use, so the app works no matter how it is launched
    (uvicorn lifespan, in-process test client, or a fresh process)."""
    global _ready
    if not _ready:
        init_db()
        conn = connect()
        try:
            # Seed if EITHER table is empty, so a partially-seeded cloud database
            # heals itself. load() upserts by primary key (idempotent) and falls
            # back to in-process synth generation when data/*.json isn't shipped
            # (e.g. a backend-only cloud build), so this works everywhere.
            n_cust = conn.execute("SELECT COUNT(*) AS c FROM customers").fetchone()["c"]
            n_pay = conn.execute("SELECT COUNT(*) AS c FROM payments").fetchone()["c"]
            if n_cust == 0 or n_pay == 0:
                load(conn)
        finally:
            conn.close()
        # In single-service cloud deploys, drain the outbox in-process.
        import os

        if os.getenv("RUN_WORKER", "").lower() in ("1", "true", "yes"):
            from .worker import start_background

            start_background()
        _ready = True
    return connect()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mode": {
            "gateway": "razorpay_test" if settings.use_real_gateway else "mock",
            "llm": "gemini" if settings.gemini_enabled else ("local" if settings.local_enabled else "mock"),
            "webhook_signature": settings.require_webhook_signature or bool(settings.razorpay_webhook_secret),
        },
    }


@app.post("/webhook/razorpay")
async def webhook(request: Request, x_razorpay_signature: str | None = Header(default=None)) -> dict:
    from .webhook import verify

    raw = await request.body()
    ok, mode = verify(raw, x_razorpay_signature)
    if not ok:
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    payload = json.loads(raw.decode("utf-8"))
    event_id = payload.get("id") or request.headers.get("x-razorpay-event-id")
    if not event_id:
        raise HTTPException(status_code=400, detail="missing event id")
    kind = payload.get("event", "unknown")

    conn = _db()
    try:
        # Dedup: store raw event once.
        dup = conn.execute("SELECT 1 FROM events WHERE event_id=?", (event_id,)).fetchone()
        if dup:
            audit.append(conn, "WEBHOOK_DUPLICATE", {"event_id": event_id, "verify_mode": mode})
            rec = conn.execute("SELECT * FROM recoveries WHERE id=?", (event_id,)).fetchone()
            return {"deduplicated": True, "recovery": dict(rec) if rec else None}

        conn.execute(
            "INSERT INTO events (event_id, kind, payload_json, received_at) VALUES (?,?,?,?)",
            (event_id, kind, raw.decode("utf-8"), _now()),
        )
        audit.append(conn, "WEBHOOK_RECEIVED", {"event_id": event_id, "kind": kind, "verify_mode": mode})

        if kind != "payment.failed":
            return {"ignored": True, "reason": f"not a payment.failed event ({kind})"}

        # Extract the payment from the Razorpay payload shape, or a flat demo shape.
        p = _extract_payment(conn, payload)
        if p is None:
            raise HTTPException(status_code=422, detail="could not resolve payment from payload")

        rec = agent.process_failed_payment(conn, event_id, p)
        return {"recovery": rec}
    finally:
        conn.close()


def _extract_payment(conn, payload):
    """Resolve a payment row. Supports the real Razorpay entity shape and a
    simplified demo shape that references a synthetic payment id."""
    # Demo shape: {"id": "...", "event": "payment.failed", "payment_id": "pay_0007"}
    if "payment_id" in payload:
        return conn.execute("SELECT * FROM payments WHERE id=?", (payload["payment_id"],)).fetchone()
    # Real shape: payload["payload"]["payment"]["entity"]
    try:
        entity = payload["payload"]["payment"]["entity"]
    except (KeyError, TypeError):
        return None
    pid = entity["id"]
    existing = conn.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if existing:
        return existing
    # Persist an unknown-but-real failed payment so the loop can act on it.
    conn.execute(
        "INSERT OR REPLACE INTO payments (id, order_id, customer_id, amount_paise, method, status, failure_reason, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            pid, entity.get("order_id", pid), entity.get("notes", {}).get("customer_id", "cust_000"),
            entity["amount"], entity.get("method", "unknown"), "failed",
            entity.get("error_reason") or "unknown", _now(),
        ),
    )
    return conn.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()


# ---- Demo drivers ----------------------------------------------------------

@app.post("/demo/simulate-failure/{payment_id}")
def simulate_failure(payment_id: str) -> dict:
    """Run a SINGLE failed payment through the live configured provider (Gemini
    if a key is set, else mock). Uses a distinct 'live_' event id so it appears
    as its own row alongside the mock batch, showcasing the real model."""
    conn = _db()
    try:
        p = conn.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        if p is None:
            raise HTTPException(status_code=404, detail="no such payment")
        event_id = f"evt_live_{payment_id}"
        conn.execute(
            "INSERT OR IGNORE INTO events (event_id, kind, payload_json, received_at) VALUES (?,?,?,?)",
            (event_id, "payment.failed", json.dumps({"payment_id": payment_id}), _now()),
        )
        # Default Router => real Gemini when configured.
        rec = agent.process_failed_payment(conn, event_id, p)
        outbox.run_once(conn, get_gateway())
        return {"recovery": rec}
    finally:
        conn.close()


@app.post("/demo/run-batch")
def run_batch() -> dict:
    """Process every failed payment in the dataset, then drain the worker once.
    This is the headline demo action.

    The bulk batch runs on the deterministic MOCK diagnoser on purpose: it makes
    the demo instant and byte-identical every time, and keeps us well under the
    serverless timeout (a real-LLM call per payment would be minutes for 88 rows).
    To showcase the live model, use POST /demo/simulate-failure/{payment_id},
    which runs a single payment through the configured provider (Gemini)."""
    from .llm.mock import MockProvider
    from .llm.router import Router

    mock_router = Router(providers=[MockProvider()])
    conn = _db()
    try:
        failed = conn.execute("SELECT * FROM payments WHERE status='failed'").fetchall()
        for p in failed:
            event_id = f"evt_{p['id']}"
            conn.execute(
                "INSERT OR IGNORE INTO events (event_id, kind, payload_json, received_at) VALUES (?,?,?,?)",
                (event_id, "payment.failed", json.dumps({"payment_id": p["id"]}), _now()),
            )
            agent.process_failed_payment(conn, event_id, p, router=mock_router)
        executed = outbox.run_once(conn, get_gateway())
        return {"processed": len(failed), "executed": executed, "metrics": metrics.compute(conn)}
    finally:
        conn.close()


@app.post("/worker/run-once")
def worker_run_once() -> dict:
    conn = _db()
    try:
        return {"executed": outbox.run_once(conn, get_gateway())}
    finally:
        conn.close()


# ---- Dashboard reads -------------------------------------------------------

@app.get("/recoveries")
def list_recoveries(limit: int = 200) -> dict:
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT r.*, e.link_id, e.short_url FROM recoveries r "
            "LEFT JOIN executions e ON e.recovery_id = r.id ORDER BY r.created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["reasons"] = json.loads(d.pop("reasons_json"))
            out.append(d)
        return {"recoveries": out}
    finally:
        conn.close()


@app.get("/recoveries/{recovery_id}")
def get_recovery(recovery_id: str) -> dict:
    conn = _db()
    try:
        r = conn.execute("SELECT * FROM recoveries WHERE id=?", (recovery_id,)).fetchone()
        if r is None:
            raise HTTPException(status_code=404, detail="not found")
        d = dict(r)
        d["reasons"] = json.loads(d.pop("reasons_json"))
        d["audit"] = [dict(a) for a in conn.execute(
            "SELECT * FROM audit WHERE recovery_id=? ORDER BY seq", (recovery_id,)
        ).fetchall()]
        ex = conn.execute("SELECT * FROM executions WHERE recovery_id=?", (recovery_id,)).fetchone()
        d["execution"] = dict(ex) if ex else None
        return d
    finally:
        conn.close()


@app.post("/recoveries/{recovery_id}/approve")
def approve(recovery_id: str) -> dict:
    conn = _db()
    try:
        rec = agent.approve(conn, recovery_id)
        outbox.run_once(conn, get_gateway())
        return {"recovery": rec}
    finally:
        conn.close()


@app.get("/metrics")
def get_metrics() -> dict:
    conn = _db()
    try:
        return metrics.compute(conn)
    finally:
        conn.close()


@app.get("/audit")
def get_audit(limit: int = 300) -> dict:
    conn = _db()
    try:
        rows = conn.execute("SELECT * FROM audit ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return {"audit": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/audit/verify")
def verify_audit() -> dict:
    conn = _db()
    try:
        ok, broken = audit.verify_chain(conn)
        return {"intact": ok, "first_broken_seq": broken}
    finally:
        conn.close()
