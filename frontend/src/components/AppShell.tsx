import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation, useParams } from "react-router-dom";
import { PanelLeftOpen } from "lucide-react";
import { setApiProject } from "../lib/api";
import { defaultProject, rememberProject, useAuth } from "../lib/auth";
import { Logo } from "./Chrome";
import { BuildStatus, useBuildPoll } from "./BuildStatus";
import { ChatList } from "./ChatList";
import { Sidebar } from "./Sidebar";

const WIDE = "(min-width: 1024px)";

function useWide() {
  const [wide, setWide] = useState(() => window.matchMedia(WIDE).matches);
  useEffect(() => {
    const m = window.matchMedia(WIDE);
    const on = () => setWide(m.matches);
    m.addEventListener("change", on);
    window.addEventListener("resize", on);
    return () => {
      m.removeEventListener("change", on);
      window.removeEventListener("resize", on);
    };
  }, []);
  return wide;
}

/** The API didn't answer at all: say so (and retry) instead of pretending the user is signed out. */
export function Offline() {
  const { refresh } = useAuth();
  useEffect(() => {
    const t = window.setInterval(refresh, 4000);
    return () => window.clearInterval(t);
  }, [refresh]);
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 px-4 text-center">
      <Logo />
      <p className="mt-4 text-h2 font-semibold">Can't reach the Warden API</p>
      <p className="max-w-[420px] text-muted">It may be starting up. This page retries every few seconds.</p>
      <button onClick={refresh} className="mt-2 inline-flex h-11 items-center rounded-full border border-line px-5 text-small font-medium hover:opacity-85">Retry now</button>
    </div>
  );
}

export function Splash() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <span className="animate-pulse">
        <Logo />
      </span>
    </div>
  );
}

/** Signed-in, project-scoped layout: sidebar (docked on desktop, a drawer on phones) + the screen. */
export function AppShell() {
  const { me, loading, offline } = useAuth();
  const { project: slug = "" } = useParams();
  const loc = useLocation();
  const wide = useWide();
  const [docked, setDocked] = useState(true);
  const [drawer, setDrawer] = useState(false);
  const project = me?.projects.find((p) => p.slug === slug);
  const buildDetail = useBuildPoll(project);

  // Every request below is scoped to this project. Set during render so children's first fetch already has it.
  if (project) setApiProject(project.slug);

  useEffect(() => {
    if (!project) return;
    rememberProject(project.slug);
  }, [project]);

  useEffect(() => setDrawer(false), [loc.pathname]);

  if (loading) return <Splash />;
  if (offline) return <Offline />;
  if (!me) return <Navigate to={`/login`} replace state={{ from: loc.pathname }} />;
  if (!project) {
    const p = defaultProject(me);
    return <Navigate to={p ? `/app/${p.slug}/home` : "/"} replace />;
  }

  const open = wide ? docked : drawer;
  const close = () => (wide ? setDocked(false) : setDrawer(false));
  // The sidebar's recent list follows the section: PR analyses on PR impact, chats everywhere else.
  const recents = loc.pathname.includes("/impact") ? (
    <ChatList kind="impact" base="/impact" label="PR analyses" />
  ) : (
    <ChatList kind="ask" base="/ask" label="Chats" />
  );
  const bar = !wide || !docked;
  return (
    // --topbar lets full-height screens (Ask) size themselves under the phone / collapsed top bar.
    <div className="flex min-h-screen bg-bg" style={{ "--topbar": bar ? "56px" : "0px" } as React.CSSProperties}>
      {wide && docked && (
        <div className="sticky top-0 h-screen shrink-0">
          <Sidebar onClose={close}>
            {recents}
          </Sidebar>
        </div>
      )}
      {!wide && drawer && (
        <div className="fixed inset-0 z-50 flex">
          <div className="rise-in h-full shadow-window">
            <Sidebar onClose={close}>
              {recents}
            </Sidebar>
          </div>
          <button className="flex-1 bg-ink/20" aria-label="Close menu" onClick={close} />
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        {!open && (
          <div className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-bg/90 px-3 backdrop-blur">
            <button onClick={() => (wide ? setDocked(true) : setDrawer(true))} className="flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:bg-code hover:text-ink" aria-label="Open sidebar">
              <PanelLeftOpen size={18} />
            </button>
            <Logo />
            <span className="ml-auto truncate text-small text-muted">{project.name}</span>
          </div>
        )}
        <main className="min-w-0 flex-1">
          {/* Until the graph is built there is nothing to show but the build; settings stay reachable to change the repo. */}
          {project.status !== "ready" && !loc.pathname.includes("/settings") ? (
            <BuildStatus
              project={project}
              detail={buildDetail}
              canEdit={["owner", "admin"].includes(me.orgs.find((o) => o.id === project.org_id)?.role ?? "")}
              settings={`/app/${project.slug}/settings/projects`}
            />
          ) : (
            <Outlet key={`${project.slug}:${project.status_detail ?? ""}`} />
          )}
        </main>
      </div>
    </div>
  );
}

/** Old flat URLs (/ask, /approvals…) land in the user's last project. */
export function ToProject({ path }: { path?: string }) {
  const { me, loading, offline } = useAuth();
  const loc = useLocation();
  if (loading) return <Splash />;
  if (offline) return <Offline />;
  if (!me) return <Navigate to="/login" replace />;
  const p = defaultProject(me);
  return <Navigate to={p ? `/app/${p.slug}${path ?? loc.pathname}${loc.search}` : "/"} replace />;
}
