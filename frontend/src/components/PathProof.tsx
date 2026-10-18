import { useMemo, useState } from "react";
import { ArrowUpRight, CheckCircle2, CircleAlert, ShieldCheck } from "lucide-react";
import { api, type Evidence, type EvidenceEdge } from "../lib/api";

const KIND: Record<string, { label: string; cls: string }> = {
  sourced: { label: "sourced", cls: "border-ink text-ink" },
  inferred: { label: "inferred", cls: "border-accent text-accent" },
  curated: { label: "curated", cls: "border-line text-muted" },
};

/** One row per hop of an attack path: what connects what, where that fact comes from, and whether it is sourced or inferred.
 *  "Validate" re-checks every hop against the live graph (read-only). */
export function PathProof({ evidence, title = "How each hop is known", compact }: { evidence: Evidence; title?: string; compact?: boolean }) {
  const [state, setState] = useState<{ busy: boolean; valid?: boolean; checked?: number; missing?: string[]; ms?: number; error?: string }>({ busy: false });
  const names = useMemo(() => new Map(evidence.nodes.map((n) => [n.id, n])), [evidence]);
  const rows = useMemo(() => {
    const order = (e: EvidenceEdge) => Math.min(names.get(e.source)?.order ?? 99, names.get(e.target)?.order ?? 99);
    return [...evidence.edges].filter((e) => e.provenance).sort((a, b) => order(a) - order(b));
  }, [evidence, names]);
  if (!rows.length) return null;
  const inferred = rows.filter((r) => r.provenance!.kind === "inferred").length;

  const validate = () => {
    setState({ busy: true });
    api
      .validateEvidence(rows.map((r) => r.id))
      .then((v) => setState({ busy: false, valid: v.valid, checked: v.checked, missing: v.hops.filter((h) => !h.present).map((h) => h.edge), ms: v.ms }))
      .catch((e: Error) => setState({ busy: false, error: e.message }));
  };

  return (
    <section className="rounded-card border border-line bg-bg">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-2.5">
        <h3 className="text-[13px] font-semibold">{title}</h3>
        <span className="text-[12px] text-muted">
          {rows.length} hops · {rows.length - inferred} sourced{inferred ? ` · ${inferred} inferred` : ""}
        </span>
        <button onClick={validate} disabled={state.busy} className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-full border border-line px-3 text-[12px] font-medium hover:border-ink disabled:opacity-50">
          <ShieldCheck size={13} /> {state.busy ? "Checking…" : "Validate in graph"}
        </button>
      </header>
      {(state.valid !== undefined || state.error) && (
        <p className={`flex items-center gap-2 border-b border-line px-4 py-2 text-[12.5px] ${state.valid ? "text-ok" : "text-accent"}`} role="status">
          {state.error ? (
            state.error
          ) : state.valid ? (
            <>
              <CheckCircle2 size={14} /> All {state.checked} hops exist in the live graph (re-queried in {state.ms} ms, read-only).
            </>
          ) : (
            <>
              <CircleAlert size={14} /> {state.missing?.length} of {state.checked} hops no longer exist: the graph changed since this path was drawn.
            </>
          )}
        </p>
      )}
      <ol className="divide-y divide-line">
        {rows.map((e) => {
          const p = e.provenance!;
          const k = KIND[p.kind];
          return (
            <li key={e.id} className={`flex flex-col gap-1 px-4 py-2.5 ${compact ? "" : "sm:flex-row sm:items-start sm:gap-3"}`}>
              <span className={`flex min-w-0 items-center gap-1.5 text-[12.5px] ${compact ? "" : "sm:w-[330px] sm:shrink-0"}`}>
                <span className="truncate font-medium">{names.get(e.source)?.name}</span>
                <span className="shrink-0 rounded bg-code px-1.5 py-0.5 font-mono text-[10.5px] text-muted">{e.type}</span>
                <span className="truncate font-medium">{names.get(e.target)?.name}</span>
              </span>
              <span className="min-w-0 flex-1 text-[12.5px] text-muted">
                {p.url ? (
                  <a href={p.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-ink hover:underline">
                    {p.source} <ArrowUpRight size={11} />
                  </a>
                ) : (
                  p.source
                )}
                {p.note && <span className="block text-[11.5px]">{p.note}</span>}
              </span>
              <span className={`inline-flex h-5 shrink-0 items-center rounded-full border px-2 text-[10.5px] font-medium ${k.cls}`}>{k.label}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
