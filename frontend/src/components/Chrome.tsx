import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { ApiError, type Health } from "../lib/api";
import { Button } from "./ui";

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

/** Live graph status in the top strip (replaces the reference's announcement bar). */
export function StatusBar({ health, error }: { health: Health | null; error: Error | null }) {
  let text: ReactNode = "Connecting to FalkorDB…";
  if (error || health?.status === "down") {
    // 503 = the API is up but FalkorDB isn't; anything else = the API itself is unreachable.
    const dbDown = health?.status === "down" || (error instanceof ApiError && error.status === 503);
    text = (
      <>
        <span className="mr-2 inline-block h-1.5 w-1.5 rounded-full bg-accent align-middle" />
        {dbDown ? `FalkorDB unreachable · ${health?.error ?? error?.message}` : "Warden API unreachable · start it and reload"}
      </>
    );
  } else if (health) {
    const parts = [
      health.graph,
      `${health.nodes?.toLocaleString()} nodes · ${health.edges?.toLocaleString()} edges`,
      health.ingest && `${health.ingest.ref} (${health.ingest.sha.slice(0, 7)}) synced ${shortDate(health.ingest.at)}`,
      health.kev && `KEV feed ${health.kev.version}`,
    ].filter(Boolean);
    text = (
      <>
        <span className="mr-2 inline-block h-1.5 w-1.5 rounded-full bg-ok align-middle" />
        {parts.join(" · ")}
        {health.browser_url && (
          <a href={health.browser_url} target="_blank" rel="noreferrer" className="ml-3 inline-flex items-center gap-0.5 text-white/70 hover:text-white">
            Open FalkorDB Browser <ArrowUpRight size={13} />
          </a>
        )}
      </>
    );
  }
  return <div className="flex h-9 items-center justify-center bg-ink px-4 text-center text-[13px] text-white">{text}</div>;
}

const NAV = [
  { to: "/", label: "Ask" },
  { to: "/impact", label: "PR impact" },
  { to: "/approvals", label: "Approvals" },
  { to: "/tools", label: "Tools" },
];

export function Header({ browserUrl }: { browserUrl?: string }) {
  return (
    <header className="mx-auto grid h-16 max-w-[1200px] grid-cols-[1fr_auto_1fr] items-center px-6">
      <Logo />
      <nav className="flex items-center gap-7 text-[15px]">
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end
            className={({ isActive }) => (isActive ? "font-medium text-ink" : "text-muted transition-colors hover:text-ink")}
          >
            {n.label}
          </NavLink>
        ))}
      </nav>
      <div className="flex justify-end">
        {browserUrl && (
          <Button href={browserUrl} icon={<ArrowUpRight size={16} />}>
            Graph
          </Button>
        )}
      </div>
    </header>
  );
}
