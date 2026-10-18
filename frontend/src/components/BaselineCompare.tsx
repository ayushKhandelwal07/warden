import { useState } from "react";
import { ArrowRight, ChevronDown } from "lucide-react";
import type { Baseline, BaselineRow } from "../lib/api";

/** One line per exposure: where it sits in this ranking and where the other ranking puts it. */
function CompactRow({ r, rank, side }: { r: BaselineRow; rank: number; side: "baseline" | "graph" }) {
  const other = side === "baseline" ? r.graph_rank : r.baseline_rank;
  const moved = other - rank;
  return (
    <li className="flex items-center gap-2 px-4 py-2 text-[13px]">
      <span className="w-5 shrink-0 text-right text-[12px] tabular-nums text-muted">{rank}</span>
      {r.kev ? <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" title="On CISA KEV" /> : <span className="h-1.5 w-1.5 shrink-0" />}
      <span className="min-w-0 flex-1 truncate">
        <span className="font-mono">{r.vuln}</span> <span className="text-muted">{r.service}</span>
      </span>
      <span className="hidden shrink-0 text-[12px] tabular-nums text-muted sm:inline">{side === "baseline" ? `CVSS ${r.cvss ?? "n/a"}` : `risk ${r.risk}`}</span>
      <span className={`w-[92px] shrink-0 text-right text-[12px] tabular-nums ${Math.abs(moved) > 9 ? "font-medium text-ink" : "text-muted"}`}>
        {side === "baseline" ? "graph" : "CVSS"} #{other}
      </span>
    </li>
  );
}

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

const SHORT = 5;

/** The same exposures ranked two ways: by severity alone (or severity with CISA KEV first) and by Warden's graph-informed risk. */
export function BaselineCompare({ data }: { data: Baseline }) {
  const [kevFirst, setKevFirst] = useState(false);
  const [full, setFull] = useState(false);
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
        <div className="border-t border-line bg-code/40 px-4 py-3">
          <p className="text-[12px] font-medium text-muted">Nearly the same CVSS ({h.scanner_pick.cvss} vs {h.graph_pick.cvss}), very different risk</p>
          <div className="mt-2 grid items-stretch gap-2 sm:grid-cols-[1fr_auto_1fr]">
            <div className="rounded-card border border-line bg-bg px-3 py-2">
              <p className="font-mono text-[12.5px]">{h.scanner_pick.vuln}</p>
              <p className="text-[12px] text-muted">{h.scanner_pick.service} · risk {h.scanner_pick.risk}</p>
            </div>
            <div className="flex items-center justify-center text-[12px] font-semibold tabular-nums text-accent">
              <ArrowRight size={14} className="mr-1 shrink-0" /> {h.risk_ratio}× higher
            </div>
            <div className="rounded-card border border-accent bg-bg px-3 py-2">
              <p className="font-mono text-[12.5px]">{h.graph_pick.vuln}</p>
              <p className="text-[12px] text-muted">{h.graph_pick.service} · risk {h.graph_pick.risk}</p>
            </div>
          </div>
          <p className="mt-2 text-[12px] text-muted">{h.graph_pick.why.join("; ")}</p>
        </div>
      )}

      <div className="grid gap-px border-t border-line bg-line lg:grid-cols-2">
        <div className="bg-bg">
          <p className="border-b border-line bg-code/40 px-4 py-2 text-[12px] font-medium text-muted">{kevFirst ? "CISA KEV first, then CVSS" : "CVSS only"} · top {full ? data.n : SHORT}</p>
          <ol className="divide-y divide-line">
            {left.slice(0, full ? data.n : SHORT).map((r, i) =>
              full ? <Row key={`${r.vuln}-${r.service}`} r={r} rank={i + 1} side="baseline" /> : <CompactRow key={`${r.vuln}-${r.service}`} r={r} rank={i + 1} side="baseline" />,
            )}
          </ol>
        </div>
        <div className="bg-bg">
          <p className="border-b border-line bg-code/40 px-4 py-2 text-[12px] font-medium text-muted">Warden graph risk · top {full ? data.n : SHORT}</p>
          <ol className="divide-y divide-line">
            {data.graph_top.slice(0, full ? data.n : SHORT).map((r, i) =>
              full ? <Row key={`${r.vuln}-${r.service}`} r={r} rank={i + 1} side="graph" /> : <CompactRow key={`${r.vuln}-${r.service}`} r={r} rank={i + 1} side="graph" />,
            )}
          </ol>
        </div>
      </div>
      <button onClick={() => setFull((f) => !f)} aria-expanded={full} className="flex w-full items-center justify-center gap-1.5 border-t border-line px-4 py-2.5 text-[12.5px] font-medium text-muted hover:bg-code/50 hover:text-ink">
        {full ? "Show fewer" : `Show the full top ${data.n}, with the reason for each`} <ChevronDown size={13} className={full ? "rotate-180" : ""} />
      </button>
      <p className="border-t border-line px-4 py-2.5 text-[12px] text-muted">
        Severity-only ties break by advisory id. The graph score is {data.method.graph}. Neither ranking is tuned to the other.
      </p>
    </section>
  );
}
