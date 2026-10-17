export type EvidenceNode = {
  id: string;
  label: string;
  prefix: string;
  name: string;
  order?: number;
  props: Record<string, string | number | boolean | null>;
};

export type EvidenceEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  props: Record<string, string | number | boolean | null>;
};

export type Evidence = { nodes: EvidenceNode[]; edges: EvidenceEdge[] };

export type Health = {
  status: "ok" | "down";
  graph: string;
  browser_url?: string;
  nodes?: number;
  edges?: number;
  ingest?: { ref: string; sha: string; at: number } | null;
  kev?: { version: string; released: string; entries: number } | null;
  error?: string;
};

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";

export type Totals = {
  services: number;
  packages: number;
  vulnerabilities: number;
  kev: number;
  exposed_services: number;
  reachable_vulnerabilities: number;
  by_severity: { severity: Severity; n: number }[];
};

export type HeroFacts = {
  ingress: string;
  entry: string;
  service: string;
  direct: boolean;
  package: string;
  version: string;
  ecosystem: string;
  fixed: string | null;
  vuln: string;
  summary: string;
  severity: Severity;
  cvss: number | null;
  epss: number | null;
  epss_percentile: number | null;
  kev_name: string | null;
  kev_added: string | null;
  kev_due: string | null;
  url: string;
  hops: number;
};

export type Overview = {
  totals: Totals;
  hero: { facts: HeroFacts; evidence: Evidence; cypher: string; ms: number } | null;
};

export type ToolParam = {
  name: string;
  type: "string" | "integer" | "enum" | "string[]";
  description: string;
  default: unknown;
  choices: string[] | null;
  required: boolean;
  minimum: number | null;
  maximum: number | null;
};

export type ToolMeta = {
  name: string;
  title: string;
  description: string;
  category: string;
  example: Record<string, unknown>;
  params: ToolParam[];
};

export type ToolQuery = { cypher: string; params: Record<string, unknown>; ms: number };

export type ToolResult = {
  tool: string;
  args: Record<string, unknown>;
  summary: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  evidence: Evidence | null;
  queries: ToolQuery[];
  sources: string[];
  ms: number;
  error: string | null;
};

export type McpStatus = {
  server: { name: string; version: string };
  transport: string;
  connect_ms: number;
  tools: { name: string; title: string; read_only: boolean; params: string[] }[];
  sample_call: { tool: string; args: Record<string, unknown>; ms: number; summary: string | null };
  client_config: unknown;
};

export type PlanNumbers = { findings: number; vulnerabilities: number; kev_findings: number; risk: number };

export type PlanItem = {
  package: string;
  ecosystem: string;
  from: string;
  to: string;
  services: string[];
  owners: string[];
  vulns: string[];
  kev: boolean;
  risk_removed: number;
  reason: string;
  major?: boolean;
};

export type Plan = {
  summary: string;
  items: PlanItem[];
  before: PlanNumbers | null;
  after: PlanNumbers | null;
  removed?: { vuln: string; service: string; risk: number }[];
  added?: { vuln: string; service: string }[];
  new_advisories_on_upgraded_versions?: string[];
  rehearsal?: { graph: string; ms: number; deleted: boolean };
};

export type PatchFile = { path: string; diff: string; changed: boolean; packages: string[] };

export type ApprovalStatus = "pending" | "approved" | "approved_not_executed" | "rejected" | "failed";

export type Approval = {
  id: string;
  kind: string;
  title: string;
  summary: string;
  status: ApprovalStatus;
  created_at: number;
  requested_by: string;
  last_error?: string | null;
  decided_at?: number;
  reason?: string | null;
  payload: Plan & {
    patches?: { service: string; files: PatchFile[] }[]; pr?: number; comment?: string; risk?: string;
    trigger?: { why: string; commit?: string } | null; body?: string; title?: string; gate?: { passed: boolean; checks: { check: string; ok: boolean; detail: string }[] };
  };
  result?: { executed: boolean; reason?: string; prs?: { service: string; number: number; url: string }[]; url?: string; number?: number; labels?: string[]; reviewers?: string[] };
};

export type WatchEvent = { id: string; at: number; kind: string; text: string; link: string | null };
export type WatchState = { enabled: boolean; interval: number; branch: string | null; last_check: number | null; last_status: string; busy: boolean };
export type WatchSnapshot = { state: WatchState; events: WatchEvent[]; github?: boolean };

export type GithubStatus = { configured: boolean; target?: string; reason?: string };

export type Dependent = { service: string; hops: number; internet_facing: boolean; ingress: string | null; team: string | null };

export type ImpactReport = {
  pr: number;
  source: "history" | "fork";
  title: string;
  url: string | null;
  kind?: string;
  package?: string | null;
  services: { service: string; files: string[]; owner: string | null }[];
  depth1?: Dependent[];
  depth3?: Dependent[];
  hidden?: string[];
  chokepoints?: string[];
  incidents?: { incident: string; date: string; severity: string; title: string; same_kind_of_change: boolean; affected_here: string; lesson: string }[];
  reviewers?: { person: string; commits: number; last_touched: string; service: string; example_commit?: string | null }[];
  policies?: { policy: string; rule: string }[];
  risk: { label: "low" | "medium" | "high"; score?: number; why: string[] };
  summary: string;
  comment?: string;
  calls: ToolResult[];
};

export type DiffFinding = { vuln: string; service: string; kev: boolean; severity: Severity; package: string; hops: number; risk: number; hops_before?: number; risk_before?: number };

export type GraphDiff = {
  before: { findings: number; kev_findings: number; risk: number };
  after: { findings: number; kev_findings: number; risk: number };
  fixed: DiffFinding[];
  new: DiffFinding[];
  worse: DiffFinding[];
  dependencies: { changed: number; added: number; removed: number; moves: { change: string; services: string[] }[] };
  exposure: { added: string[]; removed: string[] };
  calls: { added: string[]; removed: string[] };
};

export type SyncRecord = GraphDiff & {
  id: string;
  from_ref: string;
  from_sha: string;
  to_ref: string;
  to_sha: string;
  ms: number;
  decisions: { decision: string; text: string; verified: boolean; remaining: number; targets: number; done_pct: number }[];
};

export type SyncStatus = { current: { ref: string; sha: string; at: number }; refs: string[]; history: SyncRecord[]; demo_ref: string };

export type WhatIf = GraphDiff & { service: string; graph: string; deleted: boolean; error?: string };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Where the API lives. Empty in dev (Vite proxies /api); set VITE_API_URL when the UI is hosted separately (Vercel). */
export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(API_BASE + path);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body.error ?? `${res.status} ${res.statusText}`);
  return body as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(API_BASE + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data.error ?? `${res.status} ${res.statusText}`);
  return data as T;
}

export const api = {
  health: () => getJson<Health>("/api/health"),
  overview: () => getJson<Overview>("/api/overview"),
  tools: () => getJson<ToolMeta[]>("/api/tools"),
  mcp: () => getJson<McpStatus>("/api/mcp"),
  runTool: (name: string, args: Record<string, unknown>) => postJson<ToolResult>(`/api/tools/${name}`, args),
  createPlan: (maxFixes = 5) => postJson<{ approval: Approval | null; plan: Plan }>("/api/plans", { max_fixes: maxFixes }),
  approvals: () => getJson<Approval[]>("/api/approvals"),
  approve: (id: string) => postJson<Approval>(`/api/approvals/${id}/approve`, {}),
  reject: (id: string, reason: string) => postJson<Approval>(`/api/approvals/${id}/reject`, { reason }),
  github: () => getJson<GithubStatus>("/api/github"),
  watch: () => getJson<WatchSnapshot>("/api/watch"),
  watchEnable: (enabled: boolean) => postJson<{ state: WatchState }>("/api/watch/enable", { enabled }),
  watchCheck: () => postJson<WatchSnapshot & { result: { ok: boolean; status?: string; synced?: boolean; proposals?: string[] } }>("/api/watch/check", {}),
  watchSimulate: (service: string, isPublic: boolean) => postJson<{ result: { changed: boolean }; events: WatchEvent[] }>("/api/watch/simulate", { service, public: isPublic }),
  syncStatus: () => getJson<SyncStatus>("/api/sync"),
  sync: (ref: string) => postJson<SyncRecord>("/api/sync", { ref }),
  whatIf: (service: string) => postJson<WhatIf>("/api/whatif", { service }),
  reset: () => postJson<{ reset: boolean; ref: string }>("/api/reset", {}),
  impact: (pr: number, source: "history" | "fork") => postJson<{ report: ImpactReport | null; approval: Approval | null; error?: string }>("/api/impact", { pr, source }),
};

/** Fired after anything that changes the approvals list, so the nav badge refreshes. */
export const APPROVALS_CHANGED = "warden:approvals-changed";
export function notifyApprovalsChanged() {
  window.dispatchEvent(new Event(APPROVALS_CHANGED));
}

