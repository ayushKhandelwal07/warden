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

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body.error ?? `${res.status} ${res.statusText}`);
  return body as T;
}

export const api = {
  health: () => getJson<Health>("/api/health"),
  overview: () => getJson<Overview>("/api/overview"),
};
