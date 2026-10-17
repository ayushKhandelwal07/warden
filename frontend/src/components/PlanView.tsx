import type { Plan } from "../lib/api";

export function Delta({ label, before, after, fmt = (n: number) => n.toLocaleString() }: { label: string; before: number; after: number; fmt?: (n: number) => string }) {
  return (
    <div className="flex flex-col gap-1 px-5 py-4">
      <span className="text-small text-muted">{label}</span>
      <span className="text-h2 font-semibold tabular-nums">
        <span className="text-muted line-through decoration-1">{fmt(before)}</span> <span className="text-muted">→</span> {fmt(after)}
      </span>
    </div>
  );
}

/** A remediation plan: measured before/after (from the rehearsal on a graph copy) and the upgrades that achieve it. */
export function PlanView({ plan }: { plan: Plan }) {
  if (!plan.before || !plan.after) return <p className="text-muted">{plan.summary}</p>;
  const b = plan.before;
  const a = plan.after;
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 divide-line rounded-card border border-line sm:grid-cols-3 sm:divide-x">
        <Delta label="Reachable findings" before={b.findings} after={a.findings} />
        <Delta label="On CISA KEV" before={b.kev_findings} after={a.kev_findings} />
        <Delta label="Total risk" before={b.risk} after={a.risk} fmt={(n) => Math.round(n).toLocaleString()} />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-small">
          <thead>
            <tr className="border-b border-line text-left text-muted">
              <th className="h-10 px-3 font-normal">#</th>
              <th className="h-10 px-3 font-normal">upgrade</th>
              <th className="h-10 px-3 font-normal">services</th>
              <th className="h-10 px-3 text-right font-normal">advisories fixed</th>
              <th className="h-10 px-3 text-right font-normal">risk removed</th>
              <th className="h-10 px-3 font-normal">why</th>
            </tr>
          </thead>
          <tbody>
            {plan.items.map((it, i) => (
              <tr key={`${it.ecosystem}:${it.package}@${it.from}`} className="border-b border-line last:border-0">
                <td className="h-12 px-3 tabular-nums text-muted">{i + 1}</td>
                <td className="h-12 px-3">
                  <span className="whitespace-nowrap font-mono text-[12.5px]">
                    {it.package} {it.from.replace(/^v/, "")} → {it.to.replace(/^v/, "")}
                  </span>
                  {it.major && <span className="ml-2 rounded-full border border-line px-2 py-0.5 text-[11px] text-muted">breaking-change risk</span>}
                </td>
                <td className="h-12 px-3">
                  {it.services.join(", ")}
                  <span className="block text-[12px] text-muted">{it.owners.join(", ")}</span>
                </td>
                <td className="h-12 px-3 text-right tabular-nums">{it.vulns.length}</td>
                <td className="h-12 px-3 text-right tabular-nums">{Math.round(it.risk_removed)}</td>
                <td className="h-12 px-3">
                  {it.kev ? <span className="font-medium text-accent">KEV · </span> : null}
                  <span className="text-muted">{it.reason}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-small text-muted">
        {plan.rehearsal && (
          <>
            Rehearsed on <span className="font-mono text-ink">{plan.rehearsal.graph}</span> (a GRAPH.COPY of the live graph, deleted afterwards) in{" "}
            {(plan.rehearsal.ms / 1000).toFixed(1)} s. The upgraded versions were checked against OSV again.{" "}
          </>
        )}
        {plan.new_advisories_on_upgraded_versions?.length ? (
          <>
            Still open on the upgraded versions: <span className="font-mono text-ink">{plan.new_advisories_on_upgraded_versions.join(", ")}</span>.
          </>
        ) : (
          "No known advisories on the upgraded versions."
        )}
      </p>
    </div>
  );
}

/** Unified diff in the locked palette: additions in ink, removals muted (no red/green). */
export function DiffBlock({ path, diff, packages }: { path: string; diff: string; packages: string[] }) {
  return (
    <div className="rounded-card bg-code">
      <div className="flex items-center justify-between gap-4 px-4 pt-3 text-[12px] text-muted">
        <span className="font-mono">{path}</span>
        <span className="truncate">{packages.join(" · ")}</span>
      </div>
      <pre className="overflow-x-auto px-4 pb-4 pt-2 font-mono [font-variant-ligatures:none] text-[12.5px] leading-[1.6]">
        {diff
          .split("\n")
          .filter((l) => !l.startsWith("---") && !l.startsWith("+++"))
          .map((l, i) => (
            <div key={i} className={l.startsWith("+") ? "font-semibold text-ink" : l.startsWith("-") ? "text-muted line-through decoration-1" : l.startsWith("@@") ? "text-muted" : "text-ink"}>
              {l || " "}
            </div>
          ))}
      </pre>
    </div>
  );
}
