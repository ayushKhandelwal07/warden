import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { Funnel as FunnelData, FunnelStage } from "../lib/api";
import { CypherBlock } from "./ui";

function Row({ s, max, accent }: { s: FunnelStage; max: number; accent?: boolean }) {
  const [open, setOpen] = useState(false);
  const w = Math.max(2, Math.round((s.n / max) * 100));
  return (
    <li className="border-b border-line last:border-0">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full flex-col gap-2 px-4 py-3.5 text-left hover:bg-code/60 sm:flex-row sm:items-center sm:gap-4">
        <span className="flex items-baseline gap-2 sm:w-[210px] sm:shrink-0">
          <span className={`text-[26px] font-semibold leading-none tracking-[-0.03em] tabular-nums ${accent ? "text-accent" : ""}`}>{s.n.toLocaleString()}</span>
          <span className="text-[12px] text-muted">{s.unit}</span>
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[14px] font-semibold">{s.label}</span>
          <span className="mt-1.5 block h-1.5 overflow-hidden rounded-full bg-line">
            <span className={`block h-full rounded-full ${accent ? "bg-accent" : "bg-ink"}`} style={{ width: `${w}%` }} />
          </span>
        </span>
        <span className="inline-flex shrink-0 items-center gap-1 text-[12px] text-muted">
          How counted <ChevronDown size={13} className={open ? "rotate-180" : ""} />
        </span>
      </button>
      {open && (
        <div className="flex flex-col gap-3 bg-code/40 px-4 pb-4 pt-1">
          <p className="max-w-[760px] text-[13px] leading-[1.55] text-muted">{s.definition}</p>
          <CypherBlock cypher={s.cypher} ms={s.ms} />
        </div>
      )}
    </li>
  );
}

/** Headline numbers as overlapping filters over the same advisories, plus advisory × service exposure instances.
 *  Every count is the result of the Cypher revealed under "How counted". */
export function Funnel({ data }: { data: FunnelData }) {
  const max = Math.max(...data.stages.map((s) => s.n), 1);
  const snap = data.snapshot;
  return (
    <section className="flex flex-col gap-3">
      <div className="overflow-hidden rounded-card border border-line bg-bg">
        <p className="border-b border-line bg-code/50 px-4 py-2.5 text-[12px] font-medium text-muted">
          Unique advisories · overlapping filters, not exclusive buckets
        </p>
        <ul>
          {data.stages.map((s) => (
            <Row key={s.key} s={s} max={max} accent={s.key === "kev"} />
          ))}
        </ul>
        <p className="border-t border-line bg-code/50 px-4 py-2.5 text-[12px] font-medium text-muted">Exposure instances · the unit fix plans count</p>
        <ul>
          {data.instances.map((s) => (
            <Row key={s.key} s={s} max={Math.max(...data.instances.map((x) => x.n), 1)} accent={s.key === "kev_exposures"} />
          ))}
        </ul>
      </div>
      <p className="px-1 text-[12px] text-muted">
        Snapshot: <span className="font-mono">{snap.graph}</span>
        {snap.ingest && (
          <>
            {" · "}
            <span className="font-mono">
              {snap.ingest.ref} {snap.ingest.sha.slice(0, 7)}
            </span>
          </>
        )}
        {snap.kev_catalog && <> · CISA KEV catalog {snap.kev_catalog.version}</>}
        {" · "}graph version {snap.graph_version}
      </p>
    </section>
  );
}
