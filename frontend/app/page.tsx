"use client";

import { useEffect, useState } from "react";
import { api, rupees, type Metrics, type Recovery } from "@/lib/api";

export default function Dashboard() {
  const [health, setHealth] = useState<any>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [recs, setRecs] = useState<Recovery[]>([]);
  const [intact, setIntact] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    try {
      const [m, r, a] = await Promise.all([api.metrics(), api.recoveries(), api.auditVerify()]);
      setMetrics(m);
      setRecs(r.recoveries);
      setIntact(a.intact);
    } catch (e: any) {
      setErr(String(e.message || e));
    }
  }

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setErr(String(e.message || e)));
    refresh();
  }, []);

  async function runBatch() {
    setBusy(true);
    setErr(null);
    try {
      await api.runBatch();
      await refresh();
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function approve(id: string) {
    setBusy(true);
    try {
      await api.approve(id);
      await refresh();
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  const pct = (x: number) => (x * 100).toFixed(1) + "%";

  return (
    <div className="wrap">
      <div className="top">
        <div>
          <div className="brand">
            SALVAGE<span>.</span>
          </div>
          <div className="sub">
            AI Revenue Recovery · Razorpay Buildathon Track 03 · decides who to recover, prices it, and proves the lift
          </div>
        </div>
        {health && (
          <div className="mode">
            gateway <b>{health.mode.gateway}</b> · llm <b>{health.mode.llm}</b> · webhook-sig{" "}
            <b>{String(health.mode.webhook_signature)}</b>
          </div>
        )}
      </div>

      <div className="row" style={{ marginTop: 18 }}>
        <button className="btn" onClick={runBatch} disabled={busy}>
          {busy ? "Running…" : "Run recovery batch"}
        </button>
        <button className="btn ghost" onClick={refresh} disabled={busy}>
          Refresh
        </button>
        {intact !== null && (
          <span className="mini">
            audit chain:{" "}
            {intact ? <span className="pill-int">✓ intact</span> : <span className="pill-broken">✗ broken</span>}
          </span>
        )}
      </div>

      {err && (
        <div className="banner warn" style={{ marginTop: 14 }}>
          {err} — is the backend running on :8000? Start it with{" "}
          <code>uvicorn salvage.app:app</code>.
        </div>
      )}

      {metrics && (
        <>
          <div className="grid">
            <div className="card">
              <div className="k">Value at risk</div>
              <div className="v">{rupees(metrics.value_at_risk_paise)}</div>
              <div className="foot">across {metrics.treated.n + metrics.control.n} failed payments</div>
            </div>
            <div className="card">
              <div className="k">Incremental lift</div>
              <div className="v gold">{pct(metrics.incremental_lift)}</div>
              <div className="foot">
                treated {pct(metrics.treated_recovery_rate)} vs control {pct(metrics.control_recovery_rate)}
              </div>
            </div>
            <div className="card">
              <div className="k">Net incremental value</div>
              <div className="v green">{rupees(metrics.net_incremental_value_paise)}</div>
              <div className="foot">after {rupees(metrics.treated.incentive_cost_paise)} incentive cost</div>
            </div>
            <div className="card">
              <div className="k">Holdout control</div>
              <div className="v">{metrics.control.n}</div>
              <div className="foot">true 20% holdout, never contacted</div>
            </div>
          </div>
          <div className="banner warn">⚠ {metrics.label}</div>
        </>
      )}

      <div className="section-title">Recovery decisions</div>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Payment</th>
              <th>Cause</th>
              <th>LLM</th>
              <th>Decision</th>
              <th>Incentive</th>
              <th>Status</th>
              <th>Why</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {recs.map((r) => (
              <tr key={r.id} className={r.final_play === "do_nothing" && r.vetoed ? "refuse-row" : ""}>
                <td>
                  {r.payment_id}
                  {r.in_control_group ? <div className="mini">holdout</div> : null}
                </td>
                <td>{r.root_cause}</td>
                <td>
                  <span className={`tag ${r.llm_provider}`}>{r.llm_provider}</span>
                </td>
                <td>
                  <span className={`tag ${r.final_play}`}>{r.final_play}</span>
                  {r.vetoed ? <div className="mini">vetoed from {r.proposed_play}</div> : null}
                </td>
                <td>{r.incentive_paise > 0 ? rupees(r.incentive_paise) : "—"}</td>
                <td>
                  <span className={`tag ${r.status}`}>{r.status}</span>
                  {r.link_id ? <div className="mini">{r.link_id}</div> : null}
                </td>
                <td>
                  <div className="reason">{r.reasons?.[0]}</div>
                </td>
                <td>
                  {r.status === "awaiting_approval" && (
                    <button className="btn" onClick={() => approve(r.id)} disabled={busy}>
                      Approve
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {recs.length === 0 && <div className="mini" style={{ marginTop: 12 }}>No recoveries yet. Click “Run recovery batch”.</div>}
    </div>
  );
}
