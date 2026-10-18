import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { api, notifyContradictionsChanged, type Contradiction } from "../lib/api";
import { useContradictions } from "../lib/useContradictions";

const KIND: Record<string, string> = {
  toolchain: "Go toolchain",
  npm_pin: "package.json vs lockfile",
  range: "Advisory range",
  exposure: "Exposure label",
  decision: "Verified decision",
};

function Row({ c }: { c: Contradiction }) {
  return (
    <li className="border-b border-line px-4 py-3 last:border-0">
      <p className="flex flex-wrap items-center gap-x-2 text-[13px]">
        <span className="rounded-full border border-accent px-2 py-0.5 text-[11px] text-accent">{KIND[c.kind] ?? c.kind}</span>
        <span className="min-w-0 flex-1">{c.detail}</span>
      </p>
      <p className="mt-1 text-[12px] text-muted">{c.resolution}</p>
      <p className="mt-0.5 font-mono text-[11px] text-muted">{c.sources.join("  ≠  ")}</p>
    </li>
  );
}

/** Where two of our own sources disagree. Plans that touch these abstain until they are resolved. */
export function ContradictionsPanel() {
  const { items, loading } = useContradictions();
  const [st, setSt] = useState<{ busy: boolean; checked?: Record<string, number>; error?: string }>({ busy: false });
  const scan = () => {
    setSt({ busy: true });
    api.scanContradictions().then(
      (r) => {
        setSt({ busy: false, checked: r.checked });
        notifyContradictionsChanged();
      },
      (e: Error) => setSt({ busy: false, error: e.message }),
    );
  };
  const total = st.checked ? Object.values(st.checked).reduce((a, b) => a + b, 0) : null;
  return (
    <section className="overflow-hidden rounded-card border border-line bg-bg">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-[14px] font-semibold">Evidence contradictions · {loading ? "…" : items.length}</h3>
          <p className="text-[12px] text-muted">Places where our own sources disagree. A fix that depends on a disputed fact is blocked, not guessed.</p>
        </div>
        <button onClick={scan} disabled={st.busy} className="inline-flex h-8 items-center gap-1.5 rounded-full border border-line px-3 text-[12.5px] font-medium hover:bg-code/60 disabled:opacity-40">
          <RefreshCw size={13} className={st.busy ? "animate-spin" : ""} /> {st.busy ? "Checking…" : "Re-check sources"}
        </button>
      </header>
      {st.error && <p className="px-4 py-2 text-small text-accent">{st.error}</p>}
      {!loading && items.length === 0 ? (
        <p className="px-4 py-3 text-[13px] text-muted">
          {total !== null ? `Checked ${total} facts across go.mod, Dockerfiles, package.json, lockfiles, advisories, labels and decisions: the sources agree.` : "No open contradiction: the sources Warden checked agree."}
        </p>
      ) : (
        <ul>
          {items.map((c) => (
            <Row key={c.id} c={c} />
          ))}
        </ul>
      )}
    </section>
  );
}
