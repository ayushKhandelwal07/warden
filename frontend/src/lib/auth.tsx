import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError, UNAUTHORIZED, type Me, type Project } from "./api";

type Auth = {
  me: Me | null;
  /** True until the first /api/auth/me answer. */
  loading: boolean;
  /** Set when the API itself is unreachable (not just signed out). */
  offline: boolean;
  setMe: (m: Me | null) => void;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

const Ctx = createContext<Auth | null>(null);
const LAST_PROJECT = "warden:last-project";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const m = await api.me();
      setMe(m.user ? (m as Me) : null);
      setOffline(false);
    } catch (e) {
      setMe(null);
      setOffline(!(e instanceof ApiError) || e.status >= 500);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const drop = () => setMe(null);
    window.addEventListener(UNAUTHORIZED, drop);
    return () => window.removeEventListener(UNAUTHORIZED, drop);
  }, [refresh]);

  const logout = useCallback(async () => {
    await api.logout().catch(() => undefined);
    setMe(null);
  }, []);

  const value = useMemo(() => ({ me, loading, offline, setMe, refresh, logout }), [me, loading, offline, refresh, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const a = useContext(Ctx);
  if (!a) throw new Error("useAuth outside AuthProvider");
  return a;
}

export function rememberProject(slug: string) {
  try {
    localStorage.setItem(LAST_PROJECT, slug);
  } catch {
    /* private mode: fine, we fall back to the first project */
  }
}

/** The project to open when a URL doesn't name one: the last one used, else the first. */
export function defaultProject(me: Me): Project | undefined {
  let last: string | null = null;
  try {
    last = localStorage.getItem(LAST_PROJECT);
  } catch {
    last = null;
  }
  return me.projects.find((p) => p.slug === last) ?? me.projects[0];
}

/** The current project (from the URL) and a helper that builds links inside it. */
export function useProject() {
  const { project: slug = "" } = useParams();
  const { me } = useAuth();
  const project = me?.projects.find((p) => p.slug === slug) ?? null;
  const to = useCallback((path: string) => `/app/${slug}${path.startsWith("/") ? path : `/${path}`}`, [slug]);
  return { slug, project, to };
}
