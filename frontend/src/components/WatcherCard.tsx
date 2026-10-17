import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Eye, FlaskConical, RotateCcw, ScanSearch } from "lucide-react";
import { api, notifyApprovalsChanged, type WatchSnapshot } from "../lib/api";

const KIND_DOT: Record<string, string> = { proposal: "bg-accent", verified: "bg-ok", merged: "bg-ok", gate: "bg-ink", change: "bg-muted", sync: "bg-muted", watch: "bg-line" };

function ago(ms: number | null) {
  if (!ms) return "never";
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)}m ago` : `${Math.round(s / 3600)}h ago`;
}

/** The autonomous watcher: on/off, a manual check, a one-click real change on the fork, and what it did on its own. */
export function WatcherCard({ onChange }: { onChange?: () => void }) {
  const [snap, setSnap] = useState<WatchSnapshot | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [, tick] = useState(0);

  const load = () => api.watch().then(setSnap).catch((e: Error) => setMsg(e.message));
  useEffect(() => {
    load();
    const t = window.setInterval(() => {
      load();
      tick((n) => n + 1);
    }, 5000);
    return () => window.clearInterval(t);
  }, []);

  const run = (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setMsg(null);
    fn()
      .then(() => {
        load();
        notifyApprovalsChanged();
        onChange?.();
      })
      .catch((e: Error) => setMsg(e.message))
      .finally(() => setBusy(null));
  };

  const st = snap?.state;
  const off = !!snap && !snap.github;
  return (
    <section className="rounded-window border border-line">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <Eye size={16} className={st?.enabled ? "text-accent" : "text-muted"} />
        <div className="min-w-0 flex-1">
          <p className="text-small font-medium">Watcher {st?.enabled ? "is on" : "is off"}</p>
          <p className="truncate text-[12px] text-muted">
            {off ? "Connect GitHub to watch your fork" : st ? `${st.branch ?? "main"} · ${st.last_status} · ${ago(st.last_check)}` : "Loading…"}
          </p>
        </div>
        <button
          role="switch"
          aria-checked={!!st?.enabled}
          disabled={!snap || off || !!busy}
          onClick={() => run("toggle", () => api.watchEnable(!st?.enabled))}
          className={`relative h-7 w-12 shrink-0 rounded-full transition-colors disabled:opacity-40 ${st?.enabled ? "bg-ink" : "bg-line"}`}
          aria-label="Toggle watcher"
        >
          <span className={`absolute top-1 h-5 w-5 rounded-full bg-white transition-all ${st?.enabled ? "left-6" : "left-1"}`} />
        </button>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-line px-4 py-3">
        <button disabled={!!busy || off} onClick={() => run("check", () => api.watchCheck())} className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3.5 text-[12.5px] font-medium hover:border-ink disabled:opacity-40">
          <ScanSearch size={14} /> {busy === "check" ? "Checking…" : "Check now"}
        </button>
        <button disabled={!!busy || off} onClick={() => run("expose", () => api.watchSimulate("paymentservice", true))} className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3.5 text-[12.5px] font-medium hover:border-ink disabled:opacity-40" title="Commits a one-line change to your fork: paymentservice becomes internet-facing">
          <FlaskConical size={14} /> {busy === "expose" ? "Committing…" : "Make paymentservice public"}
        </button>
        <button disabled={!!busy || off} onClick={() => run("undo", () => api.watchSimulate("paymentservice", false))} className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3.5 text-[12.5px] text-muted hover:text-ink disabled:opacity-40">
          <RotateCcw size={14} /> Undo
        </button>
      </div>
      {msg && <p className="px-4 pt-3 text-small text-accent">{msg}</p>}

      <ul className="divide-y divide-line px-4">
        {snap?.events.length ? (
          snap.events.slice(0, 6).map((e) => (
            <li key={e.id} className="flex items-start gap-3 py-2.5 text-small">
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${KIND_DOT[e.kind] ?? "bg-line"}`} />
              <span className="min-w-0 flex-1">
                {e.link?.startsWith("/") ? (
                  <Link to={e.link} className="hover:underline">
                    {e.text}
                  </Link>
                ) : e.link ? (
                  <a href={e.link} target="_blank" rel="noreferrer" className="hover:underline">
                    {e.text}
                  </a>
                ) : (
                  e.text
                )}
              </span>
              <span className="shrink-0 text-[11.5px] text-muted">{ago(e.at)}</span>
            </li>
          ))
        ) : (
          <li className="py-4 text-small text-muted">Nothing yet. Turn the watcher on, then change something on the fork.</li>
        )}
      </ul>
    </section>
  );
}
