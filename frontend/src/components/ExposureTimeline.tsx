import { useEffect, useState } from "react";
import { api, type ServiceInfo, type ToolResult } from "../lib/api";
import { useProject } from "../lib/auth";
import { useApi } from "../lib/useApi";
import { useExamples } from "../lib/useExamples";

const LABEL: Record<string, string> = {
  exposure_closed: "closed",
  exposure_opened: "opened",
  service_exposed: "exposed",
  service_unexposed: "unexposed",
  dependency_changed: "dependency",
  call_added: "call added",
  call_removed: "call removed",
  kev_listed: "CISA KEV",
  decision_approved: "approved",
  decision_approved_not_executed: "approved",
  decision_rejected: "rejected",
  decision_verified: "verified",
  decision_stale: "stale",
};

/** What happened over time to a service or an advisory: ledger events, decisions, KEV listing. History is never rewritten. */
export function ExposureTimeline() {
  const svcs = useApi(api.services);
  const ex = useExamples(useProject().slug);
  // Starts on this project's top advisory (or its first service when it has none).
  const [target, setTarget] = useState<{ kind: "vuln" | "service"; value: string } | null>(null);
  const [res, setRes] = useState<{ busy: boolean; r?: ToolResult; error?: string }>({ busy: true });
  const names: ServiceInfo[] = svcs.data ?? [];
  useEffect(() => {
    if (target || !ex) return;
    const first = ex.vuln ? { kind: "vuln" as const, value: ex.vuln } : ex.services[0] ? { kind: "service" as const, value: ex.services[0] } : null;
    if (first) setTarget(first);
    else setRes({ busy: false, error: "This graph has no services yet." });
  }, [ex, target]);

  useEffect(() => {
    if (!target) return;
    setRes({ busy: true });
    api.runTool("exposure_timeline", { [target.kind]: target.value, limit: 30 }, false).then(
      (r) => setRes({ busy: false, r }),
      (e: Error) => setRes({ busy: false, error: e.message }),
    );
  }, [target?.kind, target?.value]);

  return (
    <div className="rounded-card border border-line p-6">
      <h2 className="text-h2 font-semibold">Exposure timeline</h2>
      <p className="mt-1 text-small text-muted">The graph shows today. This is how it got here: every sync records what opened and closed. A fixed advisory is history, never active.</p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <select
          value={target?.kind === "service" ? target.value : ""}
          onChange={(e) => e.target.value && setTarget({ kind: "service", value: e.target.value })}
          className="h-9 rounded-full border border-line bg-bg px-3 text-[13px]"
          aria-label="Service"
        >
          <option value="">Pick a service…</option>
          {names.map((s) => (
            <option key={s.name}>{s.name}</option>
          ))}
        </select>
        <input
          key={target?.kind === "vuln" ? target.value : "service"}
          defaultValue={target?.kind === "vuln" ? target.value : ""}
          placeholder={`or an advisory id${ex?.vuln ? `, e.g. ${ex.vuln}` : ""}`}
          onKeyDown={(e) => {
            const v = (e.target as HTMLInputElement).value.trim();
            if (e.key === "Enter" && v) setTarget({ kind: "vuln", value: v });
          }}
          className="h-9 w-72 max-w-full rounded-full border border-line bg-bg px-3 text-[13px] placeholder:text-muted"
        />
      </div>
      {res.busy && <p className="mt-4 text-small text-muted">Reading the history…</p>}
      {res.error && <p className="mt-4 text-small text-accent">{res.error}</p>}
      {res.r?.error && <p className="mt-4 text-small text-accent">{res.r.error}</p>}
      {res.r && !res.r.error && (
        <>
          <p className="mt-4 text-small">{res.r.summary}</p>
          {res.r.rows.length > 0 && (
            <ol className="mt-3 flex flex-col gap-1.5 border-l border-line pl-4 text-small">
              {res.r.rows.map((e, i) => (
                <li key={i}>
                  <span className="text-muted">{String(e.when)}</span> ·{" "}
                  <span className={String(e.kind) === "kev_listed" || String(e.kind) === "decision_stale" ? "font-medium text-accent" : "font-medium"}>{LABEL[String(e.kind)] ?? String(e.kind)}</span>{" "}
                  <span className="text-muted">{String(e.what)}</span>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </div>
  );
}
