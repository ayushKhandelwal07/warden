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
  /** Where this hop comes from: a file or feed (sourced), configuration (inferred) or the team (curated). */
  provenance?: { kind: "sourced" | "inferred" | "curated"; source: string; url: string | null; note?: string };
};

export type Evidence = { nodes: EvidenceNode[]; edges: EvidenceEdge[] };

export type Health = {
  status: "ok" | "down";
  graph: string;
  browser_url?: string;
  graph_version?: number;
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

export type BaselineRow = { vuln: string; service: string; package: string; severity: string; cvss: number | null; risk: number; tier: string; kev: boolean;
  epss: number | null; hops: number; data: string[]; baseline_rank: number; graph_rank: number; why: string[] };
export type EvalSide = { answer: string; ok: boolean };
export type EvalScenario = { id: string; title: string; category: string; status: "ran" | "error"; error?: string; expected?: string; warden?: EvalSide; baseline?: EvalSide;
  queries?: number; ms?: number; checks?: { check: string; ok: boolean; level: string; detail: string }[] | null };
export type EvalCount = { n: number; warden: number; baseline: number };
export type EvalPr = { tp: number; fp: number; fn: number; precision: number | null; recall: number | null };
export type EvalCard = {
  at?: number; seconds?: number; scenarios: EvalScenario[]; pending: { id: string; title: string; expected: string; unlocks: string }[];
  metrics: null | { reachability: { warden: EvalPr; baseline: EvalPr }; priority: EvalCount; gate: EvalCount; abstain: EvalCount; overall: EvalCount;
    latency_ms: { queries: number; p50: number | null; p95: number | null } };
  baseline_definition?: string; limitations?: string;
};
export type PlanConstraints = { max_changes?: number; frozen_services?: string[]; no_major?: boolean; must_fix_kev?: boolean };
export type PlanRow = {
  id: string; label: string; why: string; empty?: boolean; same_as?: string | null; recommended?: boolean; pareto?: boolean;
  risk_before?: number; risk_after?: number; risk_removed?: number; risk_removed_pct?: number; changes?: number; majors?: number; new_advisories?: number;
  exposures_removed?: number; residual_kev?: number; kev_before?: number; gate?: boolean; gate_failed?: string[];
  items?: { package: string; from: string; to: string; services: string[]; kev: boolean; major: boolean; risk_removed: number }[];
  shared_win?: { package: string; to: string; exposures: number; services: number; vulns: number; top_cvss: { vuln: string; service: string; cvss: number } | null } | null;
};
export type PlanCompare = { constraints: Required<PlanConstraints>; rows: PlanRow[]; recommended: string | null; note: string };
export type Baseline = {
  universe: number; n: number; overlap: number;
  method: { unit: string; baseline: string; kev_aware: string; graph: string };
  baseline_top: BaselineRow[]; graph_top: BaselineRow[]; only_baseline: BaselineRow[]; only_graph: BaselineRow[];
  kev_aware: { top: BaselineRow[]; overlap: number; only_graph: BaselineRow[]; only_kev_aware: BaselineRow[] };
  kev_positions: BaselineRow[];
  headline: { scanner_pick: BaselineRow; graph_pick: BaselineRow; cvss_gap: number; risk_ratio: number } | null;
};

export type FunnelStage = { key: string; label: string; unit: string; definition: string; cypher: string; n: number; ms: number };
export type Funnel = {
  stages: FunnelStage[];
  instances: FunnelStage[];
  snapshot: { graph: string; ingest: { ref: string; sha: string; at: number } | null; kev_catalog: { version: string; released: string } | null; graph_version: number; intel_retrieved?: { kev: string | null; epss: string | null } };
};

export type Overview = {
  totals: Totals;
  funnel: Funnel;
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
  without_graph?: string | null;
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
  /** Served from the graph-versioned cache (same answer, the graph hasn't changed since). */
  cached?: boolean;
};

export type ToolRunSummary = { id: string; tool: string; args: Record<string, unknown>; summary: string | null; created_at: string };

export type McpStatus = {
  server: { name: string; version: string };
  transport: string;
  connect_ms: number;
  tools: { name: string; title: string; read_only: boolean; params: string[] }[];
  sample_call: { tool: string; args: Record<string, unknown>; ms: number; summary: string | null };
  client_config: unknown;
};

export type GateCheck = { check: string; ok: boolean; detail: string; level?: "block" | "warn" | "info" };
export type Gate = { passed: boolean; checks: GateCheck[] };
export type RegressionRow = { vuln?: string; service: string; severity?: string; asset?: string; sensitivity?: string; kev?: boolean; tier?: string;
  risk_before?: number | null; risk_after?: number | null; package_before?: string | null; package_after?: string | null; exposures_before?: number; exposures_after?: number };
export type RegressionKind = { before: number; after: number; removed: RegressionRow[]; remaining: RegressionRow[]; new: RegressionRow[] };
export type Regression = { kev: RegressionKind; sensitive: RegressionKind; data: RegressionKind };
export type Proof = { vuln: string; service: string; kev: boolean; package_before: string; package_after: string | null; removed: boolean; before: Evidence; after: Evidence | null };

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

export type PlanMemory = {
  notes: { decision: string; package: string; from: string; to: string; status: string; reason: string | null; by: string | null; at: number | null; state: string; why: string; action: string }[];
  changed: { from: string[]; to: string[] } | null;
};

export type Plan = {
  memory?: PlanMemory | null;
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
  verified?: boolean;
  kind: string;
  title: string;
  summary: string;
  status: ApprovalStatus;
  created_at: number;
  requested_by: string;
  last_error?: string | null;
  decided_at?: number;
  decided_by?: string;
  reason?: string | null;
  payload: Plan & {
    patches?: { service: string; files: PatchFile[] }[]; pr?: number; comment?: string; risk?: string;
    demo?: boolean; demo_kind?: string; trigger?: { why: string; commit?: string } | null; body?: string; title?: string; gate?: Gate; regression?: Regression; proof?: Proof | null; unsafe_demo?: boolean;
  };
  result?: { executed: boolean; reason?: string; prs?: { service: string; number: number; url: string }[]; url?: string; number?: number; labels?: string[]; reviewers?: string[] };
};

export type Contradiction = { id: string; kind: string; subject: string; detail: string; resolution: string; sources: string[]; status: string; service: string | null; package: string | null; vuln: string | null };
export const CONTRADICTIONS_CHANGED = "warden:contradictions";
export const notifyContradictionsChanged = () => window.dispatchEvent(new Event(CONTRADICTIONS_CHANGED));

export type SurfaceService = { name: string; hops: number | null; risk: number; exposures: number; kev: boolean; entry: boolean; reads: string[] };
export type Surface = {
  services: SurfaceService[]; assets: { name: string; sensitivity: string; weight: number }[]; calls: { from: string; to: string }[];
  kev_path: { from: string; to: string }[]; routes: { route: string[]; asset: string }[]; entry: string[]; max_risk: number;
};

export type ReplayCall = {
  tool: string; args: Record<string, unknown>; status: "same" | "changed" | "not_replayed" | "error"; queries: { cypher: string; ms: number }[];
  summary?: string | null; approval_id?: string | null; why?: string; error?: string; stored_digest?: string; now_digest?: string;
  rows_before?: number; rows_after?: number; removed?: Record<string, unknown>[]; added?: Record<string, unknown>[];
};
export type ReplaySnapshot = { graph?: string; ref?: string | null; sha?: string | null; graph_version?: number; at?: number };
export type ReplayResult = { against: string; saved: ReplaySnapshot | null; now: ReplaySnapshot; calls: ReplayCall[]; reproduced: boolean; headline: string };

export type VerificationStep = { key: string; label: string; done: boolean; detail: string; state: "done" | "todo" | "failed" | "running" };
export type Verification = {
  approval: string; steps: VerificationStep[];
  verdict: { state: string; targets: number; gone: number; remaining: { vuln: string; service: string }[] };
  checks: { pr: number; state: string; runs: { name: string; status: string; conclusion: string | null; url: string | null }[] }[];
  preflight?: { at: number; steps: { service: string; step: string; status: "passed" | "failed" | "skipped"; detail: string; ms: number }[] } | null;
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

export type ServiceInfo = { name: string; entry: boolean; calls: string[]; packages: string[] };
export type WhatIfChange = { op: "expose" | "unexpose" | "remove_dep" | "remove_call" | "upgrade"; service?: string; package?: string; from?: string; to?: string; label?: string };
export type WhatIfBest = { change: WhatIfChange; label: string; risk_after: number; risk_recovered: number; routes_removed: number; kev_after: number };
export type WhatIfResult = GraphDiff & {
  changes: WhatIfChange[]; error?: string; assumption: string;
  paths: { before: number; after: number; new: [string, string][]; removed: [string, string][] };
  sensitive: { new_assets: string[]; no_longer_reachable: string[] };
  risk: { before: number; after: number; kev_before: number; kev_after: number };
  rank_changes: { vuln: string; service: string; before: number | null; after: number | null }[];
  intervention: { tried: WhatIfBest[]; best: WhatIfBest | null } | null;
};

export type SyncStatus = { current: { ref: string; sha: string; at: number }; refs: string[]; history: SyncRecord[]; demo_ref: string };

export type WhatIf = GraphDiff & { service: string; graph: string; deleted: boolean; error?: string };

export type User = { id: string; email: string; name: string };
export type Org = { id: string; name: string; personal: boolean; role: "owner" | "admin" | "member" };
export type Project = { id: string; slug: string; name: string; org_id: string; org_name: string; graph: string; repo_url: string | null; ref: string | null; status: string; status_detail: string | null };
export type Me = { user: User; orgs: Org[]; projects: Project[] };
export type Member = { user_id: string; name: string; email: string; role: Org["role"]; joined_at: string };
export type Conversation = { id: string; kind: "ask" | "impact"; title: string; shared: boolean; mine: boolean; owner: string | null; created_at: string; updated_at: string };
export type ConversationMessage = { id: string; role: "user" | "assistant"; content: string; data: Record<string, unknown> | null; created_at: string };
export type ConversationDetail = Conversation & { messages: ConversationMessage[] };
export type InviteInfo = { org_id: string; org_name: string; role: string; invited_by: string | null };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Where the API lives. Empty in dev (Vite proxies /api); set VITE_API_URL when the UI is hosted separately (Vercel). */
export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

let project: string | null = null;
/** The project slug every request is scoped to (set by the app shell from the URL). */
export function setApiProject(slug: string | null) {
  project = slug;
}
export function apiHeaders(json = false): Record<string, string> {
  return { ...(json ? { "Content-Type": "application/json" } : {}), ...(project ? { "X-Project": project } : {}) };
}

/** Fired on any 401, so the app drops to the login screen. */
export const UNAUTHORIZED = "warden:unauthorized";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(API_BASE + path, {
    method,
    credentials: "include",
    headers: apiHeaders(body !== undefined),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && !path.startsWith("/api/auth/")) window.dispatchEvent(new Event(UNAUTHORIZED));
  if (!res.ok) throw new ApiError(res.status, data.error ?? `${res.status} ${res.statusText}`);
  return data as T;
}

const getJson = <T,>(path: string) => request<T>("GET", path);
const postJson = <T,>(path: string, body: unknown) => request<T>("POST", path, body);
const patchJson = <T,>(path: string, body: unknown) => request<T>("PATCH", path, body);
const del = <T,>(path: string) => request<T>("DELETE", path);

export const api = {
  me: () => getJson<Me | { user: null; orgs: []; projects: [] }>("/api/auth/me"),
  updateMe: (name: string) => patchJson<Me>("/api/auth/me", { name }),
  login: (email: string, password: string, invite?: string) => postJson<Me>("/api/auth/login", { email, password, invite }),
  signup: (name: string, email: string, password: string, invite?: string) => postJson<Me>("/api/auth/signup", { name, email, password, invite }),
  logout: () => postJson<{ ok: boolean }>("/api/auth/logout", {}),
  members: (org: string) => getJson<Member[]>(`/api/orgs/${org}/members`),
  createOrg: (name: string) => postJson<Me>("/api/orgs", { name }),
  createInvite: (org: string, role = "member") => postJson<{ token: string; role: string; expires_at: string }>(`/api/orgs/${org}/invites`, { role }),
  setRole: (org: string, member: string, role: string) => patchJson<Member[]>(`/api/orgs/${org}/members/${member}`, { role }),
  removeMember: (org: string, member: string) => del<{ ok: boolean }>(`/api/orgs/${org}/members/${member}`),
  createProject: (orgId: string, name: string) => postJson<Me & { project: Project }>("/api/projects", { org_id: orgId, name }),
  deleteProject: (id: string) => del<Me>(`/api/projects/${id}`),
  invite: (token: string) => getJson<InviteInfo>(`/api/invites/${token}`),
  conversations: (kind: "ask" | "impact" = "ask") => getJson<Conversation[]>(`/api/conversations?kind=${kind}`),
  conversation: (id: string) => getJson<ConversationDetail>(`/api/conversations/${id}`),
  updateConversation: (id: string, patch: { title?: string; shared?: boolean }) => patchJson<Conversation>(`/api/conversations/${id}`, patch),
  deleteConversation: (id: string) => del<{ ok: boolean }>(`/api/conversations/${id}`),
  acceptInvite: (token: string) => postJson<Me & InviteInfo>(`/api/invites/${token}/accept`, {}),
  health: () => getJson<Health>("/api/health"),
  overview: () => getJson<Overview>("/api/overview"),
  baseline: () => getJson<Baseline>("/api/baseline"),
  evalCard: () => getJson<EvalCard>("/api/eval"),
  runEval: () => postJson<EvalCard>("/api/eval/run", {}),
  validateEvidence: (edges: string[]) => postJson<{ valid: boolean; checked: number; hops: { edge: string; present: boolean; type: string | null }[]; ms: number; graph: string; at: number }>("/api/evidence/validate", { edges }),
  tools: () => getJson<ToolMeta[]>("/api/tools"),
  mcp: () => getJson<McpStatus>("/api/mcp"),
  runTool: (name: string, args: Record<string, unknown>, save = true) => postJson<ToolResult & { run_id?: string }>(`/api/tools/${name}${save ? "" : "?save=false"}`, args),
  toolRuns: () => getJson<ToolRunSummary[]>("/api/tool-runs"),
  toolRun: (id: string) => getJson<{ id: string; tool: string; args: Record<string, unknown>; created_at: string; result: ToolResult }>(`/api/tool-runs/${id}`),
  unsafePlan: () => postJson<Plan & { gate: Gate; unsafe_demo?: boolean; items: PlanItem[] }>("/api/plans/unsafe", {}),
  createPlan: (maxFixes = 5, pick?: { variant: string; constraints: PlanConstraints }) =>
    postJson<{ approval: Approval | null; plan: Plan; blocked?: string | null }>("/api/plans", { max_fixes: maxFixes, ...(pick ?? {}) }),
  comparePlans: (constraints: PlanConstraints) => postJson<PlanCompare>("/api/plans/compare", { constraints }),
  seedDemo: () => postJson<{ created: string[]; existing: string[] }>("/api/demo/seed", {}),
  surface: () => getJson<Surface>("/api/surface"),
  publicSurface: () => getJson<Surface>("/api/public/surface"),
  contradictions: () => getJson<{ items: Contradiction[] }>("/api/contradictions"),
  scanContradictions: () => postJson<{ open: number; checked: Record<string, number>; items: Contradiction[] }>("/api/contradictions/scan", {}),
  replay: (chat: string, turn: number, against: "current" | "golden") => postJson<ReplayResult>(`/api/replay/${chat}/${turn}`, { against }),
  verification: (id: string) => getJson<Verification>(`/api/approvals/${id}/verification`),
  preflight: (id: string) => postJson<{ preflight: Verification["preflight"] }>(`/api/approvals/${id}/preflight`, {}),
  mergePr: (id: string, pr: number) => postJson<{ merged: boolean; sha: string | null; message: string | null }>(`/api/approvals/${id}/merge`, { pr }),
  approvals: () => getJson<Approval[]>("/api/approvals"),
  approval: (id: string) => getJson<Approval>(`/api/approvals/${id}`),
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
  services: () => getJson<ServiceInfo[]>("/api/services"),
  whatIfChanges: (changes: WhatIfChange[], findBest = true) => postJson<WhatIfResult>("/api/whatif", { changes, find_best: findBest }),
  reset: () => postJson<{ reset: boolean; ref: string }>("/api/reset", {}),
  impact: (pr: number, source: "history" | "fork") => postJson<{ report: ImpactReport | null; approval: Approval | null; error?: string; run_id?: string }>("/api/impact", { pr, source }),
};

/** Fired after a chat or PR analysis is created, renamed, shared or deleted, so the sidebar list refreshes. */
export const CONVERSATIONS_CHANGED = "warden:conversations-changed";
export function notifyConversationsChanged() {
  window.dispatchEvent(new Event(CONVERSATIONS_CHANGED));
}

/** Fired after anything that changes the approvals list, so the nav badge refreshes. */
export const APPROVALS_CHANGED = "warden:approvals-changed";
export function notifyApprovalsChanged() {
  window.dispatchEvent(new Event(APPROVALS_CHANGED));
}

