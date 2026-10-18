import { useEffect, useState, type ReactNode } from "react";
import { FlaskConical, Plus, X } from "lucide-react";
import { api, type GraphDiff, type ServiceInfo, type WhatIfChange, type WhatIfResult } from "../lib/api";
import { useApi } from "../lib/useApi";
import { AttackSurfaceMap } from "./AttackSurfaceMap";
import { Delta } from "./PlanView";

const OPS: { op: WhatIfChange["op"]; label: string }[] = [
  { op: "expose", label: "Expose a service to the internet" },
  { op: "unexpose", label: "Remove a service from the public ingress" },
  { op: "remove_call", label: "Stop one service calling another" },
  { op: "remove_dep", label: "Remove a package from a service" },
  { op: "upgrade", label: "Upgrade a package to a fixed version" },
];

const select = "h-9 rounded-full border border-line bg-bg px-3 text-[13px] text-ink";

function describe(c: WhatIfChange): string {
  return {
    expose: `expose ${c.service} to the internet`,
    unexpose: `remove ${c.service} from the public ingress`,
    remove_dep: `remove ${c.package} from ${c.service}`,
    remove_call: `stop ${c.from} calling ${c.to}`,
    upgrade: `upgrade ${c.package} to a fixed version`,
  }[c.op];
}

/** Counterfactuals: stack hypothetical changes, rehearse them on a copy of the graph, see paths, risk and the best counter-move. */
export function WhatIfBuilder({ renderDiff }: { renderDiff: (d: GraphDiff) => ReactNode }) {
  const svcs = useApi(api.services);
  const list: ServiceInfo[] = svcs.data ?? [];
  const names = list.map((s) => s.name);
  const packages = [...new Set(list.flatMap((s) => s.packages))].sort();
  const [op, setOp] = useState<WhatIfChange["op"]>("expose");
  const [svc, setSvc] = useState("paymentservice");
  const [to, setTo] = useState("paymentservice");
  const [from, setFrom] = useState("checkoutservice");
  const [pkg, setPkg] = useState("golang.org/x/net");
  const [changes, setChanges] = useState<WhatIfChange[]>([]);
  const [st, setSt] = useState<{ busy: boolean; r?: WhatIfResult; error?: string }>({ busy: false });

  const current = (): WhatIfChange =>
    op === "remove_call" ? { op, from, to } : op === "upgrade" ? { op, package: pkg } : op === "remove_dep" ? { op, service: svc, package: pkg } : { op, service: svc };
  const add = () => setChanges((c) => (c.length < 6 ? [...c, current()] : c));
  const run = () => {
    const use = changes.length ? changes : [current()];
    if (!changes.length) setChanges(use);
    setSt({ busy: true });
    api.whatIfChanges(use).then(
      (r) => setSt(r.error ? { busy: false, error: r.error } : { busy: false, r }),
      (e: Error) => setSt({ busy: false, error: e.message }),
    );
  };
  const r = st.r;
  const best = r?.intervention?.best;
  useEffect(() => {
    // Show the example straight away: "expose paymentservice" is the story in one click.
    if (!names.length || st.r || st.busy || changes.length) return;
    const first: WhatIfChange = { op: "expose", service: names.includes("paymentservice") ? "paymentservice" : names[0] };
    setChanges([first]);
    setSt({ busy: true });
    api.whatIfChanges([first]).then((x) => setSt({ busy: false, r: x }), (e: Error) => setSt({ busy: false, error: e.message }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [names.length]);

  return (
    <div className="rounded-card border border-line p-6">
      <h2 className="text-h2 font-semibold">What if…?</h2>
      <p className="mt-1 text-small text-muted">Stack changes, rehearse them on a copy of the graph, then delete it. Nothing in the live graph changes.</p>
      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-[12px] text-muted">
          Change
          <select className={select} value={op} onChange={(e) => setOp(e.target.value as WhatIfChange["op"])}>
            {OPS.map((o) => (
              <option key={o.op} value={o.op}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        {op === "remove_call" ? (
          <>
            <label className="flex flex-col gap-1 text-[12px] text-muted">
              From
              <select className={select} value={from} onChange={(e) => setFrom(e.target.value)}>
                {names.map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[12px] text-muted">
              To
              <select className={select} value={to} onChange={(e) => setTo(e.target.value)}>
                {names.map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
          </>
        ) : (
          op !== "upgrade" && (
            <label className="flex flex-col gap-1 text-[12px] text-muted">
              Service
              <select className={select} value={svc} onChange={(e) => setSvc(e.target.value)}>
                {names.map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
          )
        )}
        {(op === "remove_dep" || op === "upgrade") && (
          <label className="flex flex-col gap-1 text-[12px] text-muted">
            Package
            <select className={`${select} max-w-[220px]`} value={pkg} onChange={(e) => setPkg(e.target.value)}>
              {packages.map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
        )}
        <button onClick={add} disabled={changes.length >= 6} className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3 text-[13px] font-medium hover:bg-code/60 disabled:opacity-40">
          <Plus size={14} /> Add to the list
        </button>
        <button onClick={run} disabled={st.busy || !names.length} className="inline-flex h-9 items-center gap-1.5 rounded-full bg-ink px-4 text-[13px] font-medium text-white disabled:opacity-40">
          <FlaskConical size={14} /> {st.busy ? "Rehearsing…" : "Rehearse"}
        </button>
      </div>
      {changes.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {changes.map((c, i) => (
            <li key={i} className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1 text-[12.5px]">
              {describe(c)}
              <button aria-label="Remove" onClick={() => setChanges(changes.filter((_, j) => j !== i))} className="text-muted hover:text-ink">
                <X size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {st.error && <p className="mt-4 text-small text-accent">{st.error}</p>}
      {r && (
        <div className="rise-in mt-6 flex flex-col gap-6">
          <div className="grid grid-cols-1 divide-line rounded-card border border-line sm:grid-cols-3 sm:divide-x">
            <Delta label="Internet → sensitive data paths" before={r.paths.before} after={r.paths.after} />
            <Delta label="Total risk" before={r.risk.before} after={r.risk.after} fmt={(n) => Math.round(n).toLocaleString()} />
            <Delta label="KEV exposures" before={r.risk.kev_before} after={r.risk.kev_after} />
          </div>
          <AttackSurfaceMap whatIfPaths={r.paths.new} compact />
          {(r.paths.new.length > 0 || r.paths.removed.length > 0 || r.sensitive.new_assets.length > 0) && (
            <div className="grid gap-6 md:grid-cols-2">
              <div>
                <h3 className="mb-1 text-small font-medium text-muted">New paths to PCI/PII data · {r.paths.new.length}</h3>
                <ul className="flex flex-col gap-1 font-mono text-[12.5px]">
                  {r.paths.new.map((p) => (
                    <li key={p.join()} className="text-accent">
                      {p[0]} <span className="text-muted">reads</span> {p[1]}
                    </li>
                  ))}
                  {!r.paths.new.length && <li className="font-sans text-small text-muted">None.</li>}
                </ul>
                {r.sensitive.new_assets.length > 0 && <p className="mt-1 text-small text-accent">Newly reachable data: {r.sensitive.new_assets.join(", ")}</p>}
              </div>
              <div>
                <h3 className="mb-1 text-small font-medium text-muted">Paths removed · {r.paths.removed.length}</h3>
                <ul className="flex flex-col gap-1 font-mono text-[12.5px]">
                  {r.paths.removed.map((p) => (
                    <li key={p.join()}>
                      {p[0]} <span className="text-muted">reads</span> {p[1]}
                    </li>
                  ))}
                  {!r.paths.removed.length && <li className="font-sans text-small text-muted">None.</li>}
                </ul>
                {r.sensitive.no_longer_reachable.length > 0 && <p className="mt-1 text-small text-ok">No longer reachable: {r.sensitive.no_longer_reachable.join(", ")}</p>}
              </div>
            </div>
          )}
          {r.intervention && (
            <div className="rounded-card border border-line">
              <header className="border-b border-line px-4 py-2.5">
                <h3 className="text-[13px] font-semibold">Best counter-move</h3>
                <p className="text-[12px] text-muted">Each candidate is tried on a second copy; the one that recovers the most risk wins.</p>
              </header>
              {r.intervention.tried.length === 0 ? (
                <p className="px-4 py-3 text-small text-muted">Nothing to counter: the changes created no riskier exposure.</p>
              ) : (
                <ul>
                  {r.intervention.tried.map((t) => (
                    <li key={t.label} className="flex flex-wrap items-baseline gap-x-4 gap-y-0.5 border-b border-line px-4 py-2.5 text-[13px] last:border-0">
                      <span className="min-w-0 flex-1">
                        {t.label} {best && t.label === best.label && <span className="ml-2 rounded-full border border-accent px-2 py-0.5 text-[11px] text-accent">best</span>}
                      </span>
                      <span className="tabular-nums text-muted">recovers {t.risk_recovered} risk · {t.routes_removed} path{t.routes_removed === 1 ? "" : "s"}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {r.rank_changes.length > 0 && (
            <div>
              <h3 className="mb-1 text-small font-medium text-muted">Rank changes among the top 10 exposures</h3>
              <ul className="flex flex-col gap-1 text-[12.5px]">
                {r.rank_changes.slice(0, 8).map((m) => (
                  <li key={`${m.vuln}-${m.service}`}>
                    <span className="font-mono">{m.vuln}</span> <span className="text-muted">in {m.service}</span> · #{m.before ?? "n/a"} → #{m.after ?? "gone"}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {renderDiff(r)}
          <p className="text-[12px] text-muted">{r.assumption}</p>
        </div>
      )}
    </div>
  );
}
