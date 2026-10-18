import { useState } from "react";
import { FlaskConical, RefreshCw, RotateCcw } from "lucide-react";
import { api, notifyApprovalsChanged, type DiffFinding, type GraphDiff, type SyncRecord, type WhatIf } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Delta } from "../components/PlanView";
import { Button, EmptyState, Window } from "../components/ui";

function FindingList({ title, items, empty, show = 8 }: { title: string; items: DiffFinding[]; empty: string; show?: number }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-small font-medium text-muted">
        {title} <span className="tabular-nums text-ink">{items.length}</span>
      </h3>
      {items.length === 0 ? (
        <p className="text-small text-muted">{empty}</p>
      ) : (
        <ul className="flex flex-col gap-1.5 text-small">
          {items.slice(0, show).map((f) => (
            <li key={`${f.vuln}-${f.service}`} className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-mono text-[12.5px]">{f.vuln}</span>
              {f.kev && <span className="font-medium text-accent">KEV</span>}
              <span className="text-muted">
                {f.service} · {f.package}
                {f.hops_before !== undefined && (
                  <>
                    {" "}
                    · {f.hops_before} → {f.hops} hops · risk {Math.round(f.risk_before ?? 0)} → {Math.round(f.risk)}
                  </>
                )}
              </span>
            </li>
          ))}
          {items.length > show && <li className="text-muted">and {items.length - show} more</li>}
        </ul>
      )}
    </div>
  );
}

function DiffView({ d }: { d: GraphDiff }) {
  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 divide-line rounded-card border border-line sm:grid-cols-3 sm:divide-x">
        <Delta label="Reachable exposures" before={d.before.findings} after={d.after.findings} />
        <Delta label="KEV exposures" before={d.before.kev_findings} after={d.after.kev_findings} />
        <Delta label="Total risk" before={d.before.risk} after={d.after.risk} fmt={(n) => Math.round(n).toLocaleString()} />
      </div>
      <div className="grid gap-8 lg:grid-cols-2">
        <FindingList title="Fixed" items={d.fixed} empty="No finding went away." />
        <FindingList title="New" items={d.new} empty="No new finding." />
        {d.worse.length > 0 && <FindingList title="Closer to the internet (riskier)" items={d.worse} empty="" />}
        {(d.dependencies.moves.length > 0 || d.exposure.added.length > 0 || d.calls.added.length + d.calls.removed.length > 0) && (
          <div className="flex flex-col gap-2">
            <h3 className="text-small font-medium text-muted">What changed in the graph</h3>
            <ul className="flex flex-col gap-1.5 text-small">
              {d.exposure.added.map((e) => (
                <li key={e}>
                  <span className="font-medium text-accent">now internet-facing</span> {e}
                </li>
              ))}
              {d.exposure.removed.map((e) => (
                <li key={e}>no longer internet-facing: {e}</li>
              ))}
              {[...d.calls.added.map((c) => `new call ${c}`), ...d.calls.removed.map((c) => `call removed ${c}`)].map((c) => (
                <li key={c}>{c}</li>
              ))}
              {d.dependencies.moves.slice(0, 8).map((m) => (
                <li key={m.change}>
                  <span className="font-mono text-[12.5px]">{m.change}</span> <span className="text-muted">in {m.services.length} service{m.services.length > 1 ? "s" : ""}</span>
                </li>
              ))}
              {d.dependencies.changed > 8 && (
                <li className="text-muted">
                  {d.dependencies.changed} version changes, {d.dependencies.added} packages added, {d.dependencies.removed} removed
                </li>
              )}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function SyncResult({ r }: { r: SyncRecord }) {
  return (
    <Window
      title={
        <>
          Synced <span className="font-mono">{r.from_ref}</span> → <span className="font-mono">{r.to_ref}</span>{" "}
          <span className="text-muted">
            ({r.to_sha.slice(0, 7)}) in {(r.ms / 1000).toFixed(1)} s
          </span>
        </>
      }
    >
      <div className="flex flex-col gap-6 p-6">
        <DiffView d={r} />
        {r.decisions.length > 0 && (
          <div className="flex flex-col gap-2 border-t border-line pt-5">
            <h3 className="text-small font-medium text-muted">Approved fixes, checked against the new graph</h3>
            {r.decisions.map((d) => (
              <p key={d.decision} className="text-small">
                {d.verified ? <span className="font-medium text-ok">Verified fixed</span> : <span className="font-medium">{d.done_pct}% done</span>} · {d.text}{" "}
                <span className="text-muted">
                  ({d.targets - d.remaining} of {d.targets} targeted exposures gone)
                </span>
              </p>
            ))}
          </div>
        )}
      </div>
    </Window>
  );
}

function WhatIfPanel() {
  const services = ["paymentservice", "checkoutservice", "cartservice", "emailservice", "loadgenerator"];
  const [svc, setSvc] = useState(services[0]);
  const [state, setState] = useState<{ busy: boolean; r?: WhatIf; error?: string }>({ busy: false });
  return (
    <div className="rounded-card border border-line p-6">
      <h2 className="text-h2 font-semibold">What if a service became internet-facing?</h2>
      <p className="mt-1 text-small text-muted">
        Rehearsed on a GRAPH.COPY with a public LoadBalancer added, then deleted. Nothing in the live graph changes.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {services.map((s) => (
          <button
            key={s}
            onClick={() => setSvc(s)}
            className={`h-8 rounded-full px-3 text-[12px] font-medium ${svc === s ? "bg-ink text-white" : "border border-line text-muted hover:text-ink"}`}
          >
            {s}
          </button>
        ))}
        <Button
          icon={<FlaskConical size={15} />}
          disabled={state.busy}
          onClick={() => {
            setState({ busy: true });
            api
              .whatIf(svc)
              .then((r) => setState(r.error ? { busy: false, error: r.error } : { busy: false, r }))
              .catch((e: Error) => setState({ busy: false, error: e.message }));
          }}
        >
          {state.busy ? "Rehearsing…" : "Rehearse"}
        </Button>
      </div>
      {state.error && <p className="mt-4 text-small text-accent">{state.error}</p>}
      {state.r && (
        <div className="rise-in mt-6">
          <DiffView d={state.r} />
        </div>
      )}
    </div>
  );
}

export function Sync() {
  const status = useApi(api.syncStatus);
  const [ref, setRef] = useState<string | null>(null);
  const [state, setState] = useState<{ busy: boolean; r?: SyncRecord; error?: string }>({ busy: false });
  const [confirmReset, setConfirmReset] = useState(false);

  if (status.loading) return <p className="py-24 text-center text-muted">Reading sync state…</p>;
  if (status.error || !status.data) return <EmptyState message={`Couldn't read sync state (${status.error?.message}).`} />;
  const s = status.data;
  const target = ref ?? s.refs.find((r) => r !== s.current.ref) ?? s.refs[0];

  return (
    <div className="mx-auto max-w-[1200px] px-6 pb-24">
      <section className="mx-auto max-w-[680px] pb-10 pt-16 text-center">
        <h1 className="text-h1 font-semibold">Keep the graph honest.</h1>
        <p className="mt-4 text-[17px] text-muted">
          Re-read the repo at any release and see exactly what changed.{" "}
          <span className="font-semibold text-ink">Approved fixes are checked against the new graph, not assumed.</span>
        </p>
      </section>

      <div className="mx-auto flex max-w-[860px] flex-col gap-5 rounded-card border border-line p-6">
        <p className="text-small">
          The graph reflects <span className="font-mono">{s.current.ref}</span>{" "}
          <span className="text-muted">
            ({s.current.sha?.slice(0, 7)}), synced {new Date(s.current.at).toLocaleString()}
          </span>
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-small text-muted">Sync to</span>
          {s.refs.slice(0, 8).map((r) => (
            <button
              key={r}
              onClick={() => setRef(r)}
              disabled={r === s.current.ref}
              className={`h-8 rounded-full px-3 font-mono text-[12px] disabled:opacity-40 ${target === r ? "bg-ink text-white" : "border border-line text-muted hover:text-ink"}`}
            >
              {r}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            icon={<RefreshCw size={16} />}
            disabled={state.busy || target === s.current.ref}
            onClick={() => {
              setState({ busy: true });
              api
                .sync(target)
                .then((r) => {
                  setState({ busy: false, r });
                  status.reload();
                })
                .catch((e: Error) => setState({ busy: false, error: e.message }));
            }}
          >
            {state.busy ? `Re-reading ${target}…` : `Sync to ${target}`}
          </Button>
          {s.current.ref !== s.demo_ref || s.history.length ? (
            confirmReset ? (
              <Button
                icon={<RotateCcw size={16} />}
                onClick={() =>
                  api.reset().then(() => {
                    setConfirmReset(false);
                    setState({ busy: false });
                    status.reload();
                    notifyApprovalsChanged();
                  })
                }
              >
                Confirm: back to {s.demo_ref}, clear approvals
              </Button>
            ) : (
              <Button icon={<RotateCcw size={16} />} onClick={() => setConfirmReset(true)}>
                Reset demo
              </Button>
            )
          ) : null}
        </div>
        {state.error && <p className="text-small text-accent">Sync failed: {state.error}</p>}
      </div>

      <div className="mt-10 flex flex-col gap-10">
        {state.r && <SyncResult r={state.r} />}
        <WhatIfPanel />
        {s.history.length > 0 && (
          <div className="flex flex-col gap-2">
            <h3 className="text-small font-medium text-muted">Earlier syncs</h3>
            {s.history.map((h) => (
              <p key={h.id} className="text-small">
                <span className="font-mono">
                  {h.from_ref} → {h.to_ref}
                </span>{" "}
                <span className="text-muted">
                  · {h.fixed.length} fixed · {h.new.length} new · KEV {h.before.kev_findings} → {h.after.kev_findings}
                </span>
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
