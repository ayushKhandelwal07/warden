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
  decided_by?: string;
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
  tools: () => getJson<ToolMeta[]>("/api/tools"),
  mcp: () => getJson<McpStatus>("/api/mcp"),
  runTool: (name: string, args: Record<string, unknown>, save = true) => postJson<ToolResult & { run_id?: string }>(`/api/tools/${name}${save ? "" : "?save=false"}`, args),
  toolRuns: () => getJson<ToolRunSummary[]>("/api/tool-runs"),
  toolRun: (id: string) => getJson<{ id: string; tool: string; args: Record<string, unknown>; created_at: string; result: ToolResult }>(`/api/tool-runs/${id}`),
  createPlan: (maxFixes = 5) => postJson<{ approval: Approval | null; plan: Plan }>("/api/plans", { max_fixes: maxFixes }),
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

