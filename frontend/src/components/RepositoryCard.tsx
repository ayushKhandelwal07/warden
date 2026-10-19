import { useEffect, useState } from "react";
import { GitBranch, GitFork } from "lucide-react";
import { api, type GithubRepo, type Me, type Project, type RepoChoice } from "../lib/api";

const select = "h-11 min-w-0 flex-1 rounded-full border border-line bg-bg px-4 text-small";

/** Repository + branch picker over the repos the GitHub token can push to. Shared by "New project" and the repository card. */
export function RepoPicker({ value, onChange, disabled }: { value: RepoChoice | null; onChange: (c: RepoChoice | null) => void; disabled?: boolean }) {
  const [repos, setRepos] = useState<GithubRepo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [branches, setBranches] = useState<string[]>([]);
  const repo = value ? `${value.owner}/${value.repo}` : "";

  useEffect(() => {
    api.githubRepos().then(setRepos, (e: Error) => {
      setRepos([]);
      setError(e.message);
    });
  }, []);
  useEffect(() => {
    if (!repo) return setBranches([]);
    api.githubBranches(repo).then(
      (b) => {
        setBranches(b);
        const def = repos?.find((r) => r.full_name === repo)?.default_branch;
        if (value && !b.includes(value.base)) onChange({ ...value, base: def && b.includes(def) ? def : b[0] ?? "" });
      },
      () => setBranches([]),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo, repos]);

  const pick = (full: string) => {
    const r = repos?.find((x) => x.full_name === full);
    onChange(r ? { owner: r.owner, repo: r.name, base: r.default_branch } : null);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <GitFork size={16} className="text-muted" />
        <select value={repo} onChange={(e) => pick(e.target.value)} className={select} aria-label="Repository" disabled={disabled || !repos}>
          <option value="">{repos ? (repos.length ? "Choose a repository…" : "No repositories found") : "Loading your repositories…"}</option>
          {(repos ?? []).map((r) => (
            <option key={r.full_name} value={r.full_name}>
              {r.full_name}
              {r.fork ? " (fork)" : ""}
              {r.private ? " · private" : ""}
            </option>
          ))}
        </select>
        <GitBranch size={16} className="text-muted" />
        <select value={value?.base ?? ""} onChange={(e) => value && onChange({ ...value, base: e.target.value })} className={`${select} max-w-[220px]`} aria-label="Branch" disabled={disabled || !branches.length}>
          {branches.map((b) => (
            <option key={b}>{b}</option>
          ))}
        </select>
      </div>
      {error && <p className="text-small text-accent">{error}</p>}
    </div>
  );
}

/** Which GitHub repository and branch a project reads its graph from, opens PRs on, and watches. */
export function RepositoryCard({ project, canEdit, onSaved }: { project: Project; canEdit: boolean; onSaved: (me: Me) => void }) {
  const current: RepoChoice | null = project.gh_owner && project.gh_repo ? { owner: project.gh_owner, repo: project.gh_repo, base: project.gh_base ?? "" } : null;
  const [choice, setChoice] = useState<RepoChoice | null>(current);
  const [st, setSt] = useState<{ busy: boolean; error?: string; saved?: string }>({ busy: false });
  const [check, setCheck] = useState<{ target?: string; missing?: string[]; matches?: boolean } | null>(null);
  useEffect(() => {
    api.githubCheck().then(setCheck, () => setCheck(null));
  }, [project.gh_owner, project.gh_repo, project.gh_base]);

  const changed = !!choice?.base && (choice.owner !== current?.owner || choice.repo !== current?.repo || choice.base !== current?.base);
  const rebuilds = !project.demo && changed;
  const save = async () => {
    if (!choice) return;
    setSt({ busy: true });
    try {
      const p = await api.setProjectGithub(project.id, choice.owner, choice.repo, choice.base);
      onSaved((await api.me()) as Me);
      setSt({ busy: false, saved: p.status === "ready" ? "Saved. Switch the watcher on again to follow the new branch." : "Saved. The graph is being rebuilt from this repository." });
    } catch (e) {
      setSt({ busy: false, error: (e as Error).message });
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-small text-muted">
        {project.demo
          ? "This shared project keeps the microservices-demo graph every team member uses, so it follows a fork of microservices-demo. To read any other repository, create a new project from it."
          : "This project's graph is built from this repository's code: its services, dependencies and history. Choosing another repository or branch rebuilds the graph from it."}{" "}
        {current ? (
          <>
            Now: <span className="font-mono text-ink">{current.owner}/{current.repo}</span>
            {current.base ? <> on <span className="font-mono text-ink">{current.base}</span></> : null}.
          </>
        ) : (
          "Using the repository from .env."
        )}
      </p>
      {check && check.matches === false && (
        <p className="rounded-card border border-accent px-3 py-2 text-small text-accent">
          {check.target} does not contain the code this project's graph was built from (missing {check.missing?.join(", ")}).{" "}
          {project.demo ? "Choose a fork of microservices-demo." : "Choose the repository again to rebuild the graph from it."}
        </p>
      )}
      {!canEdit ? (
        <p className="text-small text-muted">Only an owner or admin of the team can change it.</p>
      ) : (
        <div className="flex flex-wrap items-start gap-2">
          <div className="min-w-0 flex-1">
            <RepoPicker value={choice} onChange={setChoice} disabled={st.busy} />
          </div>
          <button onClick={save} disabled={st.busy || !changed} className="h-11 rounded-full border border-line bg-bg px-5 text-small font-medium text-ink hover:border-ink disabled:opacity-40">
            {st.busy ? "Saving…" : rebuilds ? "Save and rebuild" : "Save"}
          </button>
        </div>
      )}
      {st.error && <p className="text-small text-accent">{st.error}</p>}
      {st.saved && <p className="text-small text-ok">{st.saved}</p>}
    </div>
  );
}
