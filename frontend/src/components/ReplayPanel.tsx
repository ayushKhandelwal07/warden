import { useState } from "react";
import { Check, CircleAlert, Minus, RotateCcw } from "lucide-react";
import { api, type ReplayResult } from "../lib/api";

const stamp = (s?: { graph?: string; ref?: string | null; sha?: string | null; graph_version?: number; at?: number } | null) =>
  s ? `${s.graph} · ${s.ref ?? "?"}${s.sha ? ` (${s.sha.slice(0, 7)})` : ""} · write ${s.graph_version ?? "?"}` : "no snapshot was saved with this answer";

/** Re-runs the tool calls behind one answer and shows, per call, whether the graph still returns the same rows. */
export function ReplayPanel({ chatId, turn }: { chatId: string; turn: number }) {
  const [st, setSt] = useState<{ busy: boolean; r?: ReplayResult; error?: string; against: "current" | "golden" }>({ busy: false, against: "current" });
  const run = (against: "current" | "golden") => {
    setSt({ busy: true, against });
    api.replay(chatId, turn, against).then(
      (r) => setSt({ busy: false, r, against }),
      (e: Error) => setSt({ busy: false, error: e.message, against }),
    );
  };
  const r = st.r;
  return (
    <div className="mt-2 border-t border-line pt-2 text-[12px]" onClick={(e) => e.stopPropagation()}>
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={() => run("current")} disabled={st.busy} className="inline-flex items-center gap-1.5 font-medium text-ink hover:opacity-80 disabled:opacity-50">
          <RotateCcw size={12} className={st.busy ? "animate-spin" : ""} /> {st.busy ? "Replaying…" : r ? "Replay again" : "Replay this investigation"}
        </button>
        {r && (
          <button onClick={() => run(st.against === "current" ? "golden" : "current")} disabled={st.busy} className="text-muted hover:text-ink">
            {st.against === "current" ? "Against the demo snapshot instead" : "Against the current graph"}
          </button>
        )}
      </div>
      {st.error && <p className="mt-1 text-accent">{st.error}</p>}
      {r && (
        <div className="mt-2 flex flex-col gap-2">
          <p className={`flex items-center gap-1.5 font-medium ${r.reproduced ? "text-ok" : "text-accent"}`}>
            {r.reproduced ? <Check size={13} /> : <CircleAlert size={13} />} {r.headline}
          </p>
          <p className="text-muted">
            {r.saved ? `Saved against ${stamp(r.saved)}.` : "No snapshot was saved with this older answer."} Re-run against {stamp(r.now)}.
          </p>
          <ul className="flex flex-col gap-1.5">
            {r.calls.map((c, i) => (
              <li key={i} className="rounded-card border border-line px-3 py-2">
                <p className="flex flex-wrap items-center gap-x-2">
                  {c.status === "same" ? <Check size={12} className="text-ok" /> : c.status === "not_replayed" ? <Minus size={12} className="text-muted" /> : <CircleAlert size={12} className="text-accent" />}
                  <span className="font-mono">{c.tool}</span>
                  <span className="text-muted">{JSON.stringify(c.args)}</span>
                  <span className={c.status === "changed" || c.status === "error" ? "font-medium text-accent" : "text-muted"}>
                    {c.status === "not_replayed" ? "not re-run" : c.status}
                  </span>
                  {c.stored_digest && <span className="font-mono text-muted">{c.stored_digest === c.now_digest ? c.now_digest : `${c.stored_digest} → ${c.now_digest}`}</span>}
                </p>
                {c.why && <p className="text-muted">{c.why}</p>}
                {c.error && <p className="text-accent">{c.error}</p>}
                {c.status === "changed" && (
                  <div className="mt-1 grid gap-2 md:grid-cols-2">
                    <div>
                      <p className="text-muted">Gone now · {c.removed?.length ?? 0}</p>
                      {c.removed?.map((x, j) => (
                        <p key={j} className="break-words font-mono text-[11px]">{JSON.stringify(x)}</p>
                      ))}
                    </div>
                    <div>
                      <p className="text-muted">New now · {c.added?.length ?? 0}</p>
                      {c.added?.map((x, j) => (
                        <p key={j} className="break-words font-mono text-[11px]">{JSON.stringify(x)}</p>
                      ))}
                    </div>
                  </div>
                )}
                {c.queries.length > 0 && (
                  <details className="mt-1">
                    <summary className="cursor-pointer text-muted">{c.queries.length} Cypher quer{c.queries.length === 1 ? "y" : "ies"} behind it</summary>
                    {c.queries.map((q, j) => (
                      <pre key={j} className="mt-1 overflow-x-auto whitespace-pre-wrap rounded-card bg-code p-2 font-mono text-[11px]">{q.cypher}</pre>
                    ))}
                  </details>
                )}
                {c.approval_id && <p className="text-muted">Outcome: filed approval {c.approval_id} (the approval and its gate are on the Approvals page).</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
