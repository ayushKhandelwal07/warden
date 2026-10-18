import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { Check, ChevronsUpDown, GitPullRequest, House, Inbox, LogOut, MessageSquare, PanelLeftClose, Plus, ListChecks, RefreshCw, Settings, Wrench } from "lucide-react";
import type { Health } from "../lib/api";
import { useAuth, useProject } from "../lib/auth";
import { Logo, StatusDot, usePendingCount } from "./Chrome";

/** Closes a popover on outside click or Escape. */
export function useDismiss<T extends HTMLElement>(open: boolean, close: () => void) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && close();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);
  return ref;
}

function ProjectSwitcher() {
  const { me } = useAuth();
  const { project, slug } = useProject();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useDismiss<HTMLDivElement>(open, () => setOpen(false));
  if (!me || !project) return null;
  const byOrg = me.orgs
    .map((o) => ({ org: o, projects: me.projects.filter((p) => p.org_id === o.id) }))
    .filter((g) => g.projects.length > 0);
  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 rounded-card border border-line px-3 py-2 text-left transition-colors hover:bg-code"
      >
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-ink text-[12px] font-semibold text-white">{project.name[0]}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-small font-medium">{project.name}</span>
          <span className="block truncate text-[11.5px] text-muted">{project.org_name}</span>
        </span>
        <ChevronsUpDown size={15} className="shrink-0 text-muted" />
      </button>
      {open && (
        <div className="rise-in absolute inset-x-0 top-[calc(100%+6px)] z-50 rounded-card border border-line bg-bg p-1.5 shadow-window">
          {byOrg.map((g) => (
            <div key={g.org.id} className="py-1">
              <p className="px-2.5 pb-1 text-[11px] font-medium uppercase tracking-wide text-muted">{g.org.name}</p>
              {g.projects.map((p) => (
                <button
                  key={p.id}
                  onClick={() => {
                    setOpen(false);
                    nav(`/app/${p.slug}/home`);
                  }}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-small hover:bg-code"
                >
                  <span className="min-w-0 flex-1 truncate">{p.name}</span>
                  {p.slug === slug && <Check size={14} />}
                </button>
              ))}
            </div>
          ))}
          <div className="mt-1 border-t border-line pt-1.5">
            <Link to={`/app/${slug}/settings/projects`} onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-small text-muted hover:bg-code hover:text-ink">
              <Plus size={14} /> New project
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const { me, logout } = useAuth();
  const { to } = useProject();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useDismiss<HTMLDivElement>(open, () => setOpen(false));
  if (!me) return null;
  return (
    <div ref={ref} className="relative">
      {open && (
        <div className="rise-in absolute inset-x-0 bottom-[calc(100%+6px)] z-50 rounded-card border border-line bg-bg p-1.5 shadow-window">
          <Link to={to("/settings/team")} onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-small hover:bg-code">
            <Settings size={14} className="text-muted" /> Settings
          </Link>
          <button
            onClick={async () => {
              await logout();
              nav("/login", { replace: true });
            }}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-small hover:bg-code"
          >
            <LogOut size={14} className="text-muted" /> Log out
          </button>
        </div>
      )}
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-center gap-2.5 rounded-card px-2 py-2 text-left hover:bg-code">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line text-[13px] font-semibold">{me.user.name[0]?.toUpperCase()}</span>
        <span className="min-w-0 flex-1 truncate text-small font-medium">{me.user.name}</span>
        <ChevronsUpDown size={15} className="shrink-0 text-muted" />
      </button>
    </div>
  );
}

const NAV = [
  { path: "/home", label: "Home", icon: House },
  { path: "/ask", label: "Ask", icon: MessageSquare },
  { path: "/impact", label: "PR impact", icon: GitPullRequest },
  { path: "/approvals", label: "Approvals", icon: Inbox },
  { path: "/tools", label: "Tools", icon: Wrench },
  { path: "/sync", label: "Sync", icon: RefreshCw },
  { path: "/evaluation", label: "Evaluation", icon: ListChecks },
];

/** Left rail like claude.ai: project, new chat, sections, recent items (passed in), account. */
export function Sidebar({ health, healthError, onClose, children }: { health: Health | null; healthError: Error | null; onClose: () => void; children?: ReactNode }) {
  const { to } = useProject();
  const pending = usePendingCount();
  const nav = useNavigate();
  return (
    <aside className="flex h-full w-[272px] flex-col border-r border-line bg-bg">
      <div className="flex h-14 shrink-0 items-center justify-between px-4">
        <Link to={to("/home")} aria-label="Warden home">
          <Logo />
        </Link>
        <button onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-code hover:text-ink" aria-label="Close sidebar">
          <PanelLeftClose size={17} />
        </button>
      </div>
      <div className="flex flex-col gap-3 px-3">
        <ProjectSwitcher />
        <button
          onClick={() => {
            nav(to("/ask"));
          }}
          className="flex h-10 items-center gap-2 rounded-full border border-line px-4 text-small font-medium transition-colors hover:bg-code"
        >
          <Plus size={15} /> New chat
        </button>
      </div>
      <nav className="mt-4 flex flex-col gap-0.5 px-3" aria-label="Main">
        {NAV.map((n) => (
          <NavLink
            key={n.path}
            to={to(n.path)}
            end={n.path !== "/ask" && n.path !== "/impact" && n.path !== "/approvals"}
            className={({ isActive }) =>
              `flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-small transition-colors ${isActive ? "bg-code font-medium text-ink" : "text-muted hover:bg-code hover:text-ink"}`
            }
          >
            <n.icon size={16} strokeWidth={1.8} />
            <span className="flex-1">{n.label}</span>
            {n.path === "/approvals" && pending > 0 && (
              <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-ink px-1 text-[10.5px] font-medium tabular-nums text-white">{pending}</span>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="mt-4 min-h-0 flex-1 overflow-y-auto px-3">{children}</div>
      <div className="flex shrink-0 flex-col gap-2 border-t border-line p-3">
        <StatusDot health={health} error={healthError} up />
        <UserMenu />
      </div>
    </aside>
  );
}
