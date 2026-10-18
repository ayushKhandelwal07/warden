import { useState } from "react";
import { Check, X } from "lucide-react";
import { api, type PlanCompare, type PlanConstraints, type PlanRow } from "../lib/api";

const cell = "px-3 py-2.5 align-top text-[13px] tabular-nums";

function Verdict({ r }: { r: PlanRow }) {
  return r.gate ? (
    <span className="inline-flex items-center gap-1 text-ok">
      <Check size={13} /> passes
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-accent" title={r.gate_failed?.join("; ")}>
      <X size={13} /> blocked
    </span>
  );
}

/** Constrained candidate plans, each rehearsed on its own graph copy. Pick one to file it for approval. */
export function ComparePlans({ onFiled }: { onFiled: (blocked: string | null) => void }) {
  const [cons, setCons] = useState<PlanConstraints>({ max_changes: 5, no_major: false, frozen_services: [] });
  const [frozen, setFrozen] = useState("");
  const [s, setS] = useState<{ busy: boolean; data?: PlanCompare; error?: string; filing?: string }>({ busy: false });

  const build = () => ({ ...cons, frozen_services: frozen.split(/[\s,]+/).filter(Boolean) });
  const run = () => {
    setS({ busy: true });
    api.comparePlans(build()).then((data) => setS({ busy: false, data }), (e: Error) => setS({ busy: false, error: e.message }));
  };
  const file = (r: PlanRow) => {
    setS((x) => ({ ...x, filing: r.id }));
    api.createPlan(cons.max_changes ?? 5, { variant: r.id, constraints: build() }).then(
      (res) => onFiled(res.blocked ?? null),
      (e: Error) => setS((x) => ({ ...x, filing: undefined, error: e.message })),
    );
  };
  const rows = s.data?.rows ?? [];
  const win = rows.find((r) => r.shared_win)?.shared_win;

  return (
    <section className="overflow-hidden rounded-card border border-line bg-bg">
      <header className="flex flex-wrap items-end gap-x-5 gap-y-3 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1 basis-[260px]">
          <h3 className="text-[14px] font-semibold">Compare plans</h3>
          <p className="text-[12px] text-muted">Four strategies under your constraints, each rehearsed on its own copy of the graph.</p>
        </div>
        <label className="flex flex-col gap-1 text-[12px] text-muted">
          Max changes
          <select value={cons.max_changes} onChange={(e) => setCons({ ...cons, max_changes: Number(e.target.value) })} className="h-9 rounded-full border border-line bg-bg px-3 text-[13px] text-ink">
            {[1, 2, 3, 4, 5, 6, 8].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[12px] text-muted">
          Frozen services
          <input value={frozen} onChange={(e) => setFrozen(e.target.value)} placeholder="e.g. paymentservice" className="h-9 w-44 rounded-full border border-line bg-bg px-3 text-[13px] text-ink placeholder:text-muted" />
        </label>
        <label className="flex h-9 items-center gap-2 text-[13px]">
          <input type="checkbox" checked={!!cons.no_major} onChange={(e) => setCons({ ...cons, no_major: e.target.checked })} /> No major bumps
        </label>
        <button onClick={run} disabled={s.busy} className="h-9 rounded-full bg-ink px-4 text-[13px] font-medium text-white disabled:opacity-40">
          {s.busy ? "Rehearsing four plans…" : "Compare"}
        </button>
      </header>
      {s.error && <p className="px-4 py-3 text-small text-accent">{s.error}</p>}
      {s.data && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-left">
              <thead>
                <tr className="border-b border-line text-[12px] text-muted">
                  {["Strategy", "Risk removed", "Changes", "Majors", "New advisories", "KEV left", "Gate", ""].map((h) => (
                    <th key={h} className="px-3 py-2 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-line last:border-0">
                    <td className={`${cell} max-w-[240px]`}>
                      <span className="font-semibold">{r.label}</span>
                      {r.recommended && <span className="ml-2 rounded-full border border-accent px-2 py-0.5 text-[11px] text-accent">recommended</span>}
                      {r.pareto && !r.recommended && <span className="ml-2 rounded-full border border-line px-2 py-0.5 text-[11px] text-muted">pareto</span>}
                      <span className="mt-0.5 block text-[12px] font-normal text-muted">{r.why}</span>
                    </td>
                    {r.empty || r.same_as ? (
                      <td className={`${cell} text-muted`} colSpan={6}>
                        {r.empty ? "No upgrade satisfies the constraints." : `Same upgrades as “${rows.find((x) => x.id === r.same_as)?.label}”.`}
                      </td>
                    ) : (
                      <>
                        <td className={cell}>
                          {r.risk_removed} <span className="text-muted">({r.risk_removed_pct}%)</span>
                          <span className="block text-[12px] text-muted">{r.exposures_removed} exposures</span>
                        </td>
                        <td className={cell}>{r.changes}</td>
                        <td className={cell}>{r.majors}</td>
                        <td className={cell}>{r.new_advisories}</td>
                        <td className={cell}>
                          {r.residual_kev} <span className="text-muted">of {r.kev_before}</span>
                        </td>
                        <td className={cell}>
                          <Verdict r={r} />
                        </td>
                        <td className={cell}>
                          <button onClick={() => file(r)} disabled={!r.gate || !!s.filing} className="h-8 rounded-full border border-line px-3 text-[12px] font-medium hover:bg-code/60 disabled:opacity-40">
                            {s.filing === r.id ? "Filing…" : "File for approval"}
                          </button>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!s.data.recommended && <p className="border-t border-line px-4 py-2.5 text-[12.5px] text-accent">No row clears the gate and closes every KEV exposure under these constraints. Loosen one to see why.</p>}
          {win && (
            <p className="border-t border-line bg-code/40 px-4 py-2.5 text-[12.5px] text-muted">
              One <span className="font-mono text-ink">{win.package}</span> change to {win.to} clears {win.exposures} exposures ({win.vulns} advisories) across {win.services} services.
            </p>
          )}
          <p className="border-t border-line px-4 py-2 text-[12px] text-muted">{s.data.note}</p>
        </>
      )}
    </section>
  );
}
