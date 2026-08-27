// Thin client for the SALVAGE backend. Base URL is configurable so the same
// build works locally and when deployed.
export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store", ...init });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  health: () => j<any>("/health"),
  runBatch: () => j<any>("/demo/run-batch", { method: "POST" }),
  recoveries: () => j<{ recoveries: Recovery[] }>("/recoveries"),
  metrics: () => j<Metrics>("/metrics"),
  auditVerify: () => j<{ intact: boolean; first_broken_seq: number | null }>("/audit/verify"),
  approve: (id: string) => j<any>(`/recoveries/${id}/approve`, { method: "POST" }),
  recovery: (id: string) => j<any>(`/recoveries/${id}`),
};

export type Recovery = {
  id: string;
  payment_id: string;
  customer_id: string;
  amount_paise: number;
  root_cause: string;
  llm_provider: string;
  proposed_play: string;
  final_play: string;
  incentive_paise: number;
  requires_approval: number;
  vetoed: number;
  status: string;
  in_control_group: number;
  reasons: string[];
  link_id?: string;
  short_url?: string;
};

export type Metrics = {
  label: string;
  value_at_risk_paise: number;
  treated: { n: number; recovered_n: number; recovered_value_paise: number; incentive_cost_paise: number };
  control: { n: number; recovered_n: number; recovered_value_paise: number };
  treated_recovery_rate: number;
  control_recovery_rate: number;
  incremental_lift: number;
  incremental_value_paise: number;
  net_incremental_value_paise: number;
};

export const rupees = (paise: number) =>
  "₹" + (paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 });
