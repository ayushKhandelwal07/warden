import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { api, type Project } from "../lib/api";
import { useAuth } from "../lib/auth";
import { forgetExamples } from "../lib/useExamples";
import { Button } from "./ui";

/** While a project's graph is building, polls its status and refreshes the signed-in user's projects when it moves on. */
export function useBuildPoll(project: Project | undefined) {
  const { refresh } = useAuth();
  const [detail, setDetail] = useState<string | null>(project?.status_detail ?? null);
  const busy = !!project && (project.status === "queued" || project.status === "building");
  useEffect(() => {
    if (!project || !busy) return;
    let live = true;
    const t = window.setInterval(async () => {
      try {
        const p = await api.project(project.id);
        if (!live) return;
        setDetail(p.status_detail);
        if (p.status !== project.status && !(p.status === "building" && project.status === "queued")) {
          forgetExamples(project.slug);
          await refresh();
        }
      } catch {
        /* the next tick tries again */
      }
    }, 2000);
    return () => {
      live = false;
      window.clearInterval(t);
    };
  }, [project, busy, refresh]);
  return busy ? detail ?? project?.status_detail ?? null : project?.status_detail ?? null;
}

/** Shown instead of a project's screens until its graph is built (or when the build failed). */
export function BuildStatus({ project, detail, canEdit, settings }: { project: Project; detail: string | null; canEdit: boolean; settings: string }) {
  const { refresh } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const failed = project.status === "failed";
  const repo = project.repo_url?.replace("https://github.com/", "") ?? project.name;
  const retry = async () => {
    setError(null);
    try {
      await api.rebuildProject(project.id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="mx-auto flex max-w-[640px] flex-col gap-4 px-4 pt-24">
      <p className="text-small text-muted">
        <span className="font-mono text-ink">{repo}</span>
        {project.ref && <> on <span className="font-mono text-ink">{project.ref}</span></>}
      </p>
      <h1 className="text-h1 font-semibold tracking-tight">{failed ? "The graph could not be built" : "Building this project's graph"}</h1>
      {!failed && (
        <p className="flex items-center gap-2 text-body text-muted">
          <RefreshCw size={16} className="animate-spin text-ink" />
          {detail || "Waiting to start"}
        </p>
      )}
      {failed && <p className="rounded-card border border-accent px-4 py-3 text-small text-accent">{detail || "The build stopped without saying why."}</p>}
      <p className="text-small text-muted">
        Warden reads the repository's own code: services from Kubernetes manifests, a docker-compose file or the folders that hold a dependency file, then their
        packages against OSV, CISA KEV and EPSS, then the commit history. This page opens the project as soon as the graph is ready.
      </p>
      <div className="flex flex-wrap gap-2">
        {failed && canEdit && (
          <Button variant="primary" icon={<RefreshCw size={15} />} onClick={retry}>
            Try again
          </Button>
        )}
        <Link to={settings} className="inline-flex h-11 items-center rounded-full border border-line px-5 text-small font-medium hover:border-ink">
          {failed ? "Choose another repository" : "Project settings"}
        </Link>
      </div>
      {error && <p className="text-small text-accent">{error}</p>}
    </div>
  );
}
