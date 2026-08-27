"""Full API surface via a real in-process client against an isolated DB."""
from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_run_batch_produces_metrics_and_recoveries(client):
    r = client.post("/demo/run-batch")
    assert r.status_code == 200
    body = r.json()
    assert body["processed"] > 0
    m = body["metrics"]
    for k in ("value_at_risk_paise", "incremental_lift", "net_incremental_value_paise", "label"):
        assert k in m
    assert "SIMULATED" in m["label"]  # honesty banner present

    recs = client.get("/recoveries").json()["recoveries"]
    assert len(recs) > 0
    # the refusal case must be present and vetoed to do_nothing
    refuse = [r for r in recs if r["payment_id"] == "pay_hero_refuse"]
    assert refuse and refuse[0]["final_play"] == "do_nothing" and refuse[0]["vetoed"] == 1


def test_audit_chain_intact_via_api(client):
    client.post("/demo/run-batch")
    v = client.get("/audit/verify").json()
    assert v["intact"] is True


def test_approval_flow(client):
    client.post("/demo/run-batch")
    recs = client.get("/recoveries").json()["recoveries"]
    waiting = [r for r in recs if r["status"] == "awaiting_approval"]
    assert waiting, "expected at least one recovery needing approval"
    rid = waiting[0]["id"]
    out = client.post(f"/recoveries/{rid}/approve").json()
    assert out["recovery"]["status"] in ("executing", "executed")
    # after approval + worker drain, an execution/link should exist
    detail = client.get(f"/recoveries/{rid}").json()
    assert detail["execution"] is not None


def test_webhook_dedup(client):
    payload = {"id": "evt_dupe_1", "event": "payment.failed", "payment_id": "pay_hero_bankdown"}
    first = client.post("/webhook/razorpay", json=payload)
    assert first.status_code == 200
    assert "recovery" in first.json()
    second = client.post("/webhook/razorpay", json=payload)
    assert second.status_code == 200
    assert second.json().get("deduplicated") is True


def test_webhook_ignores_non_failure_events(client):
    payload = {"id": "evt_captured_1", "event": "payment.captured"}
    r = client.post("/webhook/razorpay", json=payload)
    assert r.status_code == 200
    assert r.json().get("ignored") is True
