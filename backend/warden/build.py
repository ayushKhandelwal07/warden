"""Builds a project's graph from its own repository, in a background thread.

The project's status tells the UI where it is: queued -> building (status_detail names the step) -> ready | failed.
A build replaces the project's graph, its golden snapshot (what Reset restores) and clears agent state that described
the previous code (approvals, the watcher, the last sync), since none of it applies to a different repository.
"""
import threading

from warden import config, workspaces
from warden.db import session
from warden.db.models import Project

_running: set[str] = set()
_lock = threading.Lock()


def _set(pid: str, status: str, detail: str | None):
    with session() as s:
        p = s.get(Project, pid)
        if p:
            p.status, p.status_detail = status, (detail or "")[:500]


def running(pid: str) -> bool:
    return pid in _running


def start(pid: str) -> bool:
    """Starts the build unless one is already running for this project."""
    with _lock:
        if pid in _running:
            return False
        _running.add(pid)
    threading.Thread(target=_run, args=(pid,), daemon=True, name=f"build-{pid}").start()
    return True


def _run(pid: str):
    try:
        with session() as s:
            row = s.get(Project, pid)
            if not row:
                return
            p = workspaces.project_json(row)
        if not workspaces.own_source(p):
            raise RuntimeError("This project has no repository of its own to build from.")
        repo = p["repo_url"].removeprefix("https://github.com/")
        _set(pid, "building", f"Fetching {repo}")
        with workspaces.scoped(p):
            from warden.actions import approvals
            from warden.graph.client import delete_graph
            from warden.ingest.pipeline import run

            res = run(p["ref"], fresh=True, snapshot=True, fetch=True, use_nvd=False, quiet=True,
                      progress=lambda msg: _set(pid, "building", msg))
            for g in (approvals.agents_graph(), f"{config.org_graph_name()}_prev"):
                delete_graph(g)
        found = {"kubernetes": "Kubernetes manifests", "compose": "a compose file", "code": "the code folders"}.get(res["source"], res["source"])
        n = res["services"]
        _set(pid, "ready", f"Built from {repo} ({p['ref']}, {res['sha'][:7]}): {n} service{'' if n == 1 else 's'} from {found}, "
                           f"{res['packages']} packages, {res['vulns']} advisories.")
    except Exception as e:
        _set(pid, "failed", f"{type(e).__name__}: {e}")
    finally:
        _running.discard(pid)


def resume_interrupted():
    """Builds that were queued or running when the API stopped start again."""
    from sqlalchemy import select

    with session() as s:
        ids = list(s.scalars(select(Project.id).where(Project.status.in_(("queued", "building")))))
    for pid in ids:
        start(pid)
