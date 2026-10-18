import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { Regression as RegressionData, RegressionKind, RegressionRow } from "../lib/api";

const KINDS: { key: keyof RegressionData; label: string; note: string }[] = [
  { key: "kev", label: "KEV exposures", note: "A reachable advisory on CISA KEV, per service" },
  { key: "sensitive", label: "Exposures reaching PCI/PII data", note: "A reachable advisory in a service that reads card data, addresses or emails" },
  { key: "data", label: "Sensitive data still exposed", note: "A service that reads PCI/PII data and still has any reachable exposure" },
];

function line(r: RegressionRow) {
  if (r.asset) return `${r.service} reads ${r.asset} (${r.sensitivity}): ${r.exposures_before ?? 0} → ${r.exposures_after ?? 0} exposures`;
  const move = r.package_before && r.package_after && r.package_before !== r.package_after ? ` · ${r.package_before} → ${r.package_after}` : "";
  return `${r.vuln} in ${r.service}${r.severity && r.severity !== "UNKNOWN" ? ` (${r.severity})` : ""}${move}`;
}

function Group({ label, rows, tone }: { label: string; rows: RegressionRow[]; tone: string }) {
  if (!rows.length) return null;
  const shown = rows.slice(0, 12);
  return (
    <div>
      <p className={`mb-1 text-[12px] font-medium ${tone}`}>
        {label} · {rows.length}
      </p>
      <ul className="flex flex-col gap-0.5 font-mono text-[11.5px] text-muted">
        {shown.map((r, i) => (
          <li key={i} className="break-words">
            {line(r)}
          </li>
        ))}
        {rows.length > shown.length && <li>…and {rows.length - shown.length} more</li>}
      </ul>
    </div>
  );
}

function Kind({ label, note, d }: { label: string; note: string; d: RegressionKind }) {
  const [open, setOpen] = useState(false);
  const pct = d.before ? Math.round((d.removed.length / d.before) * 100) : 0;
  return (
    <li className="border-b border-line last:border-0">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-left hover:bg-code/60">
        <span className="min-w-0 flex-1">
          <span className="block text-[13.5px] font-semibold">{label}</span>
          <span className="block text-[12px] text-muted">{note}</span>
        </span>
        <span className="text-[20px] font-semibold tabular-nums">
          {d.before} <span className="text-muted">→</span> {d.after}
        </span>
        <span className="flex flex-wrap gap-1.5 text-[11.5px]">
          <span className="rounded-full border border-ok px-2 py-0.5 text-ok">{d.removed.length} removed{d.before ? ` (${pct}%)` : ""}</span>
          <span className="rounded-full border border-line px-2 py-0.5 text-muted">{d.remaining.length} remain</span>
          <span className={`rounded-full border px-2 py-0.5 ${d.new.length ? "border-accent text-accent" : "border-line text-muted"}`}>{d.new.length} new</span>
        </span>
        <ChevronDown size={14} className={`shrink-0 text-muted ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="grid gap-4 bg-code/40 px-4 pb-4 pt-3 md:grid-cols-3">
          <Group label="Removed" rows={d.removed} tone="text-ok" />
          <Group label="Still present" rows={d.remaining} tone="text-ink" />
          <Group label="New after the fix" rows={d.new} tone="text-accent" />
          {!d.removed.length && !d.remaining.length && !d.new.length && <p className="text-[12.5px] text-muted">Nothing to compare for this kind.</p>}
        </div>
      )}
    </li>
  );
}

/** Attack-path regression: the invariant paths recorded before the fix, re-run on the rehearsed graph copy.
 *  Paths are matched by advisory × service (or service × data asset), not by node ids. */
export function Regression({ data }: { data: RegressionData }) {
  return (
    <section className="overflow-hidden rounded-card border border-line bg-bg">
      <header className="border-b border-line px-4 py-2.5">
        <h3 className="text-[13px] font-semibold">Attack-path regression</h3>
        <p className="text-[12px] text-muted">The same paths, re-queried after rehearsing the fix on a copy of the graph.</p>
      </header>
      <ul>
        {KINDS.map((k) => (
          <Kind key={k.key} label={k.label} note={k.note} d={data[k.key]} />
        ))}
      </ul>
    </section>
  );
}
