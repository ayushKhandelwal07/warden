import { useState } from "react";
import { ArrowRight } from "lucide-react";
import type { Baseline, BaselineRow } from "../lib/api";

function Row({ r, rank, side }: { r: BaselineRow; rank: number; side: "baseline" | "graph" }) {
  const other = side === "baseline" ? r.graph_rank : r.baseline_rank;
  return (
    <li className="flex gap-3 px-4 py-2.5">
      <span className="w-6 shrink-0 pt-0.5 text-right text-[12px] tabular-nums text-muted">{rank}</span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[13px]">
          {r.kev && <span className="h-1.5 w-1.5 rounded-full bg-accent" title="On CISA KEV" />}
          <span className="font-mono font-medium">{r.vuln}</span>
          <span className="text-muted">{r.service}</span>
        </span>
        <span className="mt-0.5 block text-[12px] text-muted">
          CVSS {r.cvss ?? "n/a"} · risk {r.risk} · {r.hops} hop{r.hops === 1 ? "" : "s"}
          {" · "}
          <span className={other > 10 ? "text-ink" : ""}>
            {side === "baseline" ? "graph" : "severity-only"} rank {other}
          </span>
        </span>
        {side === "graph" && r.baseline_rank !== r.graph_rank && <span className="mt-0.5 block text-[12px] text-ink/70">{r.why.join("; ")}</span>}
      </span>
    </li>
  );
}

/** The same exposures ranked two ways: by severity alone (or severity with CISA KEV first) and by Warden's graph-informed risk. */
export function BaselineCompare({ data }: { data: Baseline }) {
  const [kevFirst, setKevFirst] = useState(false);
  const left = kevFirst ? data.kev_aware.top : data.baseline_top;
  const overlap = kevFirst ? data.kev_aware.overlap : data.overlap;
  const kev = data.kev_positions;
  // Where this baseline puts the KEV exposures: by CVSS alone, or (KEV first) at the very top by construction.
  const kevRange = !kev.length ? null : kevFirst ? `1–${kev.length}` : `${Math.min(...kev.map((k) => k.baseline_rank))}–${Math.max(...kev.map((k) => k.baseline_rank))}`;
  const h = data.headline;
  return (
    <section className="overflow-hidden rounded-card border border-line bg-bg">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-[14px] font-semibold">Graph vs severity</h3>
          <p className="text-[12px] text-muted">
            The same {data.universe} exposures (advisory × service), one snapshot, ranked two ways.
          </p>
        </div>
        <div className="flex gap-1 rounded-full border border-line p-1" role="tablist" aria-label="Baseline">
          {[
            { k: false, label: "Severity only" },
            { k: true, label: "KEV first" },
          ].map((o) => (
            <button
              key={o.label}
              role="tab"
              aria-selected={kevFirst === o.k}
              onClick={() => setKevFirst(o.k)}
              className={`h-8 rounded-full px-3 text-[12px] font-medium ${kevFirst === o.k ? "bg-ink text-white" : "text-muted hover:text-ink"}`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </header>

      <div className="grid gap-px bg-line sm:grid-cols-3">
        {[
          { v: `${overlap} of ${data.n}`, l: `top ${data.n} in common` },
          { v: kevRange ?? "n/a", l: `${kevFirst ? "KEV-first" : "severity-only"} rank of the ${kev.length} KEV exposures (of ${data.universe})` },
          { v: kev.length ? `1–${Math.max(...kev.map((k) => k.graph_rank))}` : "n/a", l: "their rank in the graph ranking" },
        ].map((s) => (
          <div key={s.l} className="bg-bg px-4 py-3">
            <p className="text-[22px] font-semibold tabular-nums leading-tight">{s.v}</p>
            <p className="text-[12px] text-muted">{s.l}</p>
          </div>
        ))}
      </div>

      {h && (
        <div className="flex flex-col gap-2 border-t border-line bg-code/50 px-4 py-3 text-[13px] sm:flex-row sm:items-center sm:gap-4">
          <span className="font-medium">Nearly the same CVSS ({h.scanner_pick.cvss} vs {h.graph_pick.cvss}):</span>
          <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1 text-muted">
            <span className="font-mono text-ink">{h.scanner_pick.vuln}</span> in {h.scanner_pick.service}, risk {h.scanner_pick.risk}
            <ArrowRight size={13} className="shrink-0" />
            <span className="font-mono text-ink">{h.graph_pick.vuln}</span> in {h.graph_pick.service}, risk {h.graph_pick.risk} ({h.risk_ratio}× higher)
          </span>
          <span className="text-[12px] text-muted">{h.graph_pick.why.join("; ")}</span>
        </div>
      )}

      <div className="grid gap-px border-t border-line bg-line lg:grid-cols-2">
        <div className="bg-bg">
          <p className="border-b border-line bg-code/40 px-4 py-2 text-[12px] font-medium text-muted">{kevFirst ? "CISA KEV first, then CVSS" : "CVSS only"} · top {data.n}</p>
          <ol className="divide-y divide-line">
            {left.map((r, i) => (
              <Row key={`${r.vuln}-${r.service}`} r={r} rank={i + 1} side="baseline" />
            ))}
          </ol>
        </div>
        <div className="bg-bg">
          <p className="border-b border-line bg-code/40 px-4 py-2 text-[12px] font-medium text-muted">Warden graph risk · top {data.n}</p>
          <ol className="divide-y divide-line">
            {data.graph_top.map((r, i) => (
              <Row key={`${r.vuln}-${r.service}`} r={r} rank={i + 1} side="graph" />
            ))}
          </ol>
        </div>
      </div>
      <p className="border-t border-line px-4 py-2.5 text-[12px] text-muted">
        Severity-only ties break by advisory id. The graph score is {data.method.graph}. Neither ranking is tuned to the other.
      </p>
    </section>
  );
}
