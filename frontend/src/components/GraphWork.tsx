import type { Evidence, ToolResult } from "../lib/api";

const ALGOS: [RegExp, string][] = [
  [/algo\.SPpaths/i, "SPpaths (all-pairs paths)"],
  [/algo\.pageRank/i, "PageRank"],
  [/algo\.betweenness/i, "betweenness"],
  [/shortestPath|allShortestPaths/i, "shortest path"],
];

/** What FalkorDB did for this answer, derived from the queries the tools actually ran. */
export function GraphWork({ results, evidence }: { results: ToolResult[]; evidence: Evidence }) {
  const queries = results.flatMap((r) => r.queries ?? []);
  if (!queries.length) return null;
  const ms = Math.round(queries.reduce((a, q) => a + q.ms, 0) * 10) / 10;
  const hops = Math.max(0, ...queries.flatMap((q) => [...q.cypher.matchAll(/\*(?:\d*)\.\.(\d+)/g)].map((m) => Number(m[1]))));
  const algos = ALGOS.filter(([re]) => queries.some((q) => re.test(q.cypher))).map(([, n]) => n);
  const stats: [string, string][] = [
    ["queries", String(queries.length)],
    ["graph time", `${ms} ms`],
    ...(hops ? ([["traversal depth", `up to ${hops} hops`]] as [string, string][]) : []),
    ...(algos.length ? ([["algorithms", algos.join(", ")]] as [string, string][]) : []),
    ["drawn", `${evidence.nodes.length} nodes, ${evidence.edges.length} edges`],
  ];
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 rounded-card border border-line px-3 py-2 text-[12px] text-muted" aria-label="Graph work">
      <span className="font-medium text-ink">Graph work</span>
      {stats.map(([k, v]) => (
        <span key={k}>
          {k} <span className="tabular-nums text-ink">{v}</span>
        </span>
      ))}
    </div>
  );
}
