import { useEffect, useRef, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { api, APPROVALS_CHANGED, ApiError, type Health } from "../lib/api";

export function Logo() {
  return (
    <span className="flex items-center gap-2 text-[17px] font-semibold tracking-[-0.02em]">
      <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden>
        <path d="M12 2.5 4 5.5v6.2c0 4.6 3.3 8.6 8 9.8 4.7-1.2 8-5.2 8-9.8V5.5z" className="fill-accent" />
        <path d="M7.5 15.5 11 11l2.5 2.5L17 8" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Warden
    </span>
  );
}

function shortDate(ms: number) {
  return new Date(ms).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** One dot instead of a banner: green = graph connected, orange = down. Click for the details. */
export function StatusDot({ health, error, up }: { health: Health | null; error: Error | null; up?: boolean }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const down = !!error || health?.status === "down";
  const dbDown = health?.status === "down" || (error instanceof ApiError && error.status === 503);
  const label = down ? (dbDown ? "Graph offline" : "API offline") : health ? (health.graph_version ? `Graph live · v${health.graph_version}` : "Graph live") : "Connecting";
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen((o) => !o)} className="inline-flex h-9 items-center gap-2 rounded-full border border-line px-3 text-[12px] text-muted hover:text-ink" aria-expanded={open}>
        <span className={`h-2 w-2 rounded-full ${down ? "bg-accent" : health ? "bg-ok blink" : "bg-line"}`} />
        {label}
      </button>
      {open && (
        <div className={`rise-in absolute z-40 w-[290px] ${up ? "bottom-11 left-0" : "right-0 top-11"} rounded-card border border-line bg-bg p-4 text-small shadow-window`}>
          {down ? (
            <p>{dbDown ? `FalkorDB unreachable: ${health?.error ?? error?.message}` : "The Warden API isn't answering. Start it and reload."}</p>
          ) : health ? (
            <dl className="flex flex-col gap-1.5">
              {[
                ["Graph", health.graph],
                ["Size", `${health.nodes?.toLocaleString()} nodes · ${health.edges?.toLocaleString()} edges`],
                ["Code", health.ingest ? `${health.ingest.ref} · ${health.ingest.sha.slice(0, 7)}` : "n/a"],
                ["Synced", health.ingest ? shortDate(health.ingest.at) : "n/a"],
                ["CISA KEV", health.kev?.version ?? "n/a"],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="text-muted">{k}</dt>
                  <dd className="text-right">{v}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-muted">Connecting to FalkorDB…</p>
          )}
          {health?.browser_url && (
            <a href={health.browser_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-muted hover:text-ink">
              Open FalkorDB Browser <ArrowUpRight size={13} />
            </a>
          )}
        </div>
      )}
    </div>
  );
}

/** Pending approvals count for the nav badge; refreshes on change events and every 15 s. */
export function usePendingCount() {
  const [n, setN] = useState(0);
  useEffect(() => {
    const load = () => api.approvals().then((a) => setN(a.filter((x) => x.status === "pending").length)).catch(() => setN(0));
    load();
    const t = window.setInterval(load, 15000);
    window.addEventListener(APPROVALS_CHANGED, load);
    return () => {
      window.clearInterval(t);
      window.removeEventListener(APPROVALS_CHANGED, load);
    };
  }, []);
  return n;
}
