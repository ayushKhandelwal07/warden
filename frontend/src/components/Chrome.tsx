import { useEffect, useRef, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { ArrowUpRight, GitPullRequest, House, Inbox, MessageSquare, RefreshCw, Wrench } from "lucide-react";
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
export function StatusDot({ health, error }: { health: Health | null; error: Error | null }) {
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
  const label = down ? (dbDown ? "Graph offline" : "API offline") : health ? "Live" : "Connecting";
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen((o) => !o)} className="inline-flex h-9 items-center gap-2 rounded-full border border-line px-3 text-[12px] text-muted hover:text-ink" aria-expanded={open}>
        <span className={`h-2 w-2 rounded-full ${down ? "bg-accent" : health ? "bg-ok" : "bg-line"}`} />
        {label}
      </button>
      {open && (
        <div className="rise-in absolute right-0 top-11 z-40 w-[290px] rounded-card border border-line bg-bg p-4 text-small shadow-window">
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

const NAV = [
  { to: "/", label: "Home", icon: House },
  { to: "/ask", label: "Ask", icon: MessageSquare },
  { to: "/impact", label: "PRs", icon: GitPullRequest },
  { to: "/approvals", label: "Approvals", icon: Inbox },
  { to: "/tools", label: "Tools", icon: Wrench },
];

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

function Badge({ n }: { n: number }) {
  return n > 0 ? (
    <span className="ml-1.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-ink px-1 text-[10.5px] font-medium text-white tabular-nums">{n}</span>
  ) : null;
}

export function Header({ health, error }: { health: Health | null; error: Error | null }) {
  const pending = usePendingCount();
  return (
    <>
      <header className="sticky top-0 z-30 border-b border-line bg-bg/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1200px] items-center gap-6 px-4 sm:px-6">
          <Link to="/" aria-label="Warden home">
            <Logo />
          </Link>
          <nav className="ml-4 hidden items-center gap-6 text-[14.5px] sm:flex">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end className={({ isActive }) => (isActive ? "font-medium text-ink" : "text-muted transition-colors hover:text-ink")}>
                {n.label}
                {n.to === "/approvals" && <Badge n={pending} />}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <StatusDot health={health} error={error} />
            <Link to="/sync" className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3 text-[12.5px] font-medium hover:opacity-85">
              <RefreshCw size={14} /> <span className="hidden sm:inline">Sync</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Phones: thumb-reach tab bar */}
      <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-bg/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden" aria-label="Main">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end className={({ isActive }) => `flex h-14 flex-col items-center justify-center gap-0.5 text-[10.5px] ${isActive ? "font-medium text-ink" : "text-muted"}`}>
            <span className="relative">
              <n.icon size={19} strokeWidth={1.8} />
              {n.to === "/approvals" && pending > 0 && <span className="absolute -right-2 -top-1.5 h-4 min-w-4 rounded-full bg-accent px-1 text-center text-[10px] leading-4 text-white">{pending}</span>}
            </span>
            {n.label}
          </NavLink>
        ))}
      </nav>
    </>
  );
}
