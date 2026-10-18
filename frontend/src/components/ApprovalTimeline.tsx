import { useState } from "react";
import { Check, CircleAlert, Loader2 } from "lucide-react";
import { api, type Approval, type Verification } from "../lib/api";
import { useApi } from "../lib/useApi";

const TONE: Record<string, string> = { done: "border-ink bg-ink text-white", failed: "border-accent bg-accent text-white", running: "border-ink text-ink", todo: "border-line text-muted" };
const VERDICT: Record<string, string> = {
  verified_fixed: "Verified fixed: every promised exposure is gone from the re-read graph.",
  partially_fixed: "Partially fixed: some promised exposures are still reachable.",
  not_fixed: "Not fixed: none of the promised exposures went away.",
  waiting_for_merge: "Waiting for the PRs to be merged.",
  waiting_for_graph: "Merged. Sync the graph to measure the result.",
  unknown: "This approval promised no exposures to check.",
};

/** proposed → approved → PRs → checks → merged → graph re-read → exposures gone, measured from GitHub and the graph. */
export function ApprovalTimeline({ a }: { a: Approval }) {
  const v = useApi(() => api.verification(a.id));
  const [pf, setPf] = useState<{ busy: boolean; error?: string }>({ busy: false });
  const [merge, setMerge] = useState<{ pr?: number; busy: boolean; error?: string }>({ busy: false });
  const prs = a.result?.prs ?? [];
  const d: Verification | null = v.data;
  if (v.loading) return <p className="text-small text-muted">Checking the loop…</p>;
  if (v.error || !d) return <p className="text-small text-accent">Could not read the verification ({v.error?.message}).</p>;
  const pre = d.preflight?.steps ?? [];
  return (
    <section className="overflow-hidden rounded-card border border-line bg-bg">
      <header className="border-b border-line px-4 py-2.5">
        <h3 className="text-[13px] font-semibold">From proposal to proof</h3>
        <p className="text-[12px] text-muted">{VERDICT[d.verdict.state]}</p>
      </header>
      <ol className="grid gap-px bg-line sm:grid-cols-7">
        {d.steps.map((s, i) => (
          <li key={s.key} className="flex gap-2 bg-bg px-3 py-3 sm:flex-col">
            <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] ${TONE[s.state]}`}>
              {s.state === "done" ? <Check size={12} /> : s.state === "failed" ? <CircleAlert size={12} /> : s.state === "running" ? <Loader2 size={12} className="animate-spin" /> : i + 1}
            </span>
            <span className="min-w-0">
              <span className="block text-[12.5px] font-medium">{s.label}</span>
              <span className="block text-[11.5px] leading-snug text-muted">{s.detail}</span>
            </span>
          </li>
        ))}
      </ol>
      {d.verdict.remaining.length > 0 && d.verdict.state !== "waiting_for_merge" && (
        <p className="border-t border-line px-4 py-2.5 font-mono text-[11.5px] text-muted">
          Still reachable: {d.verdict.remaining.slice(0, 8).map((r) => `${r.vuln} in ${r.service}`).join("; ")}
          {d.verdict.remaining.length > 8 ? ` and ${d.verdict.remaining.length - 8} more` : ""}
        </p>
      )}
      {d.checks.length > 0 && (
        <ul className="border-t border-line px-4 py-2.5 text-[12.5px]">
          {d.checks.map((c) => (
            <li key={c.pr} className="flex flex-wrap gap-x-3">
              <span>PR #{c.pr}</span>
              <span className={c.state === "failure" ? "text-accent" : "text-muted"}>{c.state}</span>
              <span className="text-muted">{c.runs.map((r) => `${r.name}: ${r.conclusion ?? r.status}`).join(" · ") || "no checks reported"}</span>
            </li>
          ))}
        </ul>
      )}
      {a.status === "approved" && (
        <div className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3">
          <button
            disabled={pf.busy}
            onClick={() => {
              setPf({ busy: true });
              api.preflight(a.id).then(
                () => {
                  setPf({ busy: false });
                  v.reload();
                },
                (e: Error) => setPf({ busy: false, error: e.message }),
              );
            }}
            className="h-8 rounded-full border border-line px-3 text-[12.5px] font-medium hover:bg-code/60 disabled:opacity-40"
          >
            {pf.busy ? "Running go and npm…" : "Run local pre-flight"}
          </button>
          {prs.map((p) => (
            <span key={p.number} className="inline-flex items-center gap-2 text-[12.5px]">
              {merge.pr === p.number ? (
                <>
                  <button
                    disabled={merge.busy}
                    onClick={() => {
                      setMerge({ pr: p.number, busy: true });
                      api.mergePr(a.id, p.number).then(
                        () => {
                          setMerge({ busy: false });
                          v.reload();
                        },
                        (e: Error) => setMerge({ pr: p.number, busy: false, error: e.message }),
                      );
                    }}
                    className="h-8 rounded-full bg-ink px-3 font-medium text-white disabled:opacity-40"
                  >
                    {merge.busy ? "Merging…" : `Merge #${p.number} on the fork`}
                  </button>
                  <button onClick={() => setMerge({ busy: false })} className="text-muted hover:text-ink">
                    Cancel
                  </button>
                </>
              ) : (
                <button onClick={() => setMerge({ pr: p.number, busy: false })} className="h-8 rounded-full border border-line px-3 font-medium hover:bg-code/60">
                  Merge #{p.number} ({p.service})
                </button>
              )}
            </span>
          ))}
          {pf.error && <span className="text-[12.5px] text-accent">{pf.error}</span>}
          {merge.error && <span className="text-[12.5px] text-accent">{merge.error}</span>}
        </div>
      )}
      {pre.length > 0 && (
        <ul className="border-t border-line px-4 py-2.5 text-[12.5px]">
          {pre.map((s, i) => (
            <li key={i} className="flex flex-wrap gap-x-3">
              <span className={s.status === "failed" ? "text-accent" : s.status === "passed" ? "text-ok" : "text-muted"}>{s.status}</span>
              <span>
                {s.service}: {s.step}
              </span>
              <span className="text-muted">{s.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
