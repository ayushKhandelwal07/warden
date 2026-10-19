"""The autonomous watcher: notices change on the fork by itself, re-reads the graph, and files proposals.

Every tick:
  1. head of the fork's base branch  vs  the commit the graph was built from
  2. if they differ -> sync the graph to the fork (snapshot, re-ingest, diff, verify earlier decisions)
  3. new internet exposure     -> an issue for the owning team (path, data, policy, top findings)
     new reachable KEV/CRITICAL -> a rehearsed fix plan (only if it clears the rehearsal gate)
  4. fix PRs that got merged   -> noted; the sync above already verifies the fixes against the new graph
Nothing external happens here: proposals wait in Approvals for a human. State and events live in the agents graph.
"""
import asyncio
import re
import threading
import time
import uuid

from warden import config, planner, proposals, sync
from warden.actions import approvals, github
from warden.graph.client import db, ro, rw
from warden.tools import run_tool

_lock = threading.Lock()
INTERVAL = int(__import__("os").getenv("WATCH_INTERVAL", "30"))


def _g() -> str:
    return approvals.agents_graph()


def _now() -> int:
    return int(time.time() * 1000)


def _exists() -> bool:
    return _g() in db().list_graphs()


# ---------- state + events ----------

def state() -> dict:
    base = {"enabled": False, "interval": INTERVAL, "branch": config.gh_base(), "last_check": None, "last_status": "never checked", "busy": _lock.locked()}
    if not _exists():
        return base
    rows, _ = ro("MATCH (w:Watcher {id: 'main'}) RETURN w", graph_name=_g())
    return {**base, **(rows[0]["w"].properties if rows else {}), "busy": _lock.locked(), "interval": INTERVAL}


def _set(**props):
    rw("MERGE (w:Watcher {id: 'main'}) SET w += $p", {"p": props}, _g())


def set_enabled(on: bool) -> dict:
    props: dict = {"enabled": on}
    if on and github.configured():
        try:  # from now on "changed" means the fork moved after this moment, not "differs from the demo checkout"
            props["last_head"] = github.branch_head(config.gh_base() or "main")
        except Exception:
            pass
    _set(**props)
    event("watch", "Watcher turned on" if on else "Watcher turned off")
    return state()


def event(kind: str, text: str, link: str | None = None, eid: str | None = None):
    rw(
        "MERGE (e:WatchEvent {id: $id}) ON CREATE SET e.at = $t, e.kind = $k, e.text = $x, e.link = $l",
        {"id": eid or f"ev_{uuid.uuid4().hex[:8]}", "t": _now(), "k": kind, "x": text, "l": link},
        _g(),
    )
    rw("MATCH (e:WatchEvent) WITH e ORDER BY e.at DESC SKIP 40 DELETE e", graph_name=_g())


def events(limit: int = 12) -> list[dict]:
    if not _exists():
        return []
    rows, _ = ro("MATCH (e:WatchEvent) RETURN e.id AS id, e.at AS at, e.kind AS kind, e.text AS text, e.link AS link ORDER BY at DESC LIMIT $n", {"n": limit}, _g())
    return rows


# ---------- the demo change (simulate real-world drift on the fork) ----------

def set_exposure(service: str, public: bool) -> dict:
    """Commit a one-line infra change to the fork's base branch: make a service public (or private again).
    The file is the Kubernetes manifest the graph read the service from."""
    rows, _ = ro("MATCH (s:Service {name: $s}) RETURN s.source_url AS u", {"s": service})
    url = rows[0]["u"] if rows else None
    if not url or "/blob/" not in url or not url.endswith((".yaml", ".yml")):
        raise ValueError(f"{service} has no Kubernetes manifest in this repository to change.")
    path = url.split("/blob/", 1)[1].split("/", 1)[1]
    pattern = re.compile(rf"(kind: Service\s*\n\s*metadata:\s*\n\s*name: {re.escape(service)}\s*\n(?:[^\n]*\n)*?\s*type: )(\w+)")

    def transform(text: str) -> str:
        return pattern.sub(lambda m: m.group(1) + ("LoadBalancer" if public else "ClusterIP"), text, count=1)

    verb = "Expose" if public else "Un-expose"
    res = github.edit_file(path, config.gh_base(), transform, f"{verb} {service} {'publicly' if public else 'again'} (Warden demo change)")
    if res.get("changed"):
        event("change", f"{service} was made {'internet-facing' if public else 'internal again'} on the fork", res.get("url"))
    return res


# ---------- one tick ----------

def _issue_for_exposure(service: str, head: str) -> str:
    own = run_tool("who_owns", {"service": service})
    pol = run_tool("policies_for", {"service": service})
    top = run_tool("reachable_findings", {"service": service, "limit": 3, "paths": 0})
    team = own["rows"][0]["team"] if own["rows"] else "unowned"
    lines = [
        f"`{service}` became reachable from the internet in commit `{head[:7]}`.",
        "",
        f"- Owner: **{team}**",
        f"- Policies that apply: {', '.join(p['policy'] for p in pol['rows'] if p['applies']) or 'none'}",
        f"- {top['summary']}",
        "",
        "Top findings now reachable:",
        *[f"- {r['vuln']} ({r['severity']}) in {r['package']}, risk {r['risk']}" for r in top["rows"]],
        "",
        "_Opened by Warden after you approved it. Every line comes from a path in the org graph._",
    ]
    return "\n".join(lines)


def tick(force: bool = False) -> dict:
    if not _lock.acquire(blocking=False):
        return {"ok": False, "status": "A check is already running"}
    t0 = time.perf_counter()
    try:
        if not github.configured():
            _set(last_check=_now(), last_status="GitHub is not connected, nothing to watch")
            return {"ok": False, "status": "GitHub is not connected"}
        branch = config.gh_base() or "main"
        head = github.branch_head(branch)
        built = state().get("last_head") or sync.current_ref().get("sha")
        out: dict = {"ok": True, "head": head, "synced": False, "proposals": []}

        # fix PRs merged since last look (an event, not a decision: the sync below does the verifying). One API call.
        ours = {pr["number"]: pr for a in approvals.list_all() if a["kind"] == "fix_plan" for pr in (a.get("result") or {}).get("prs", [])}
        if ours:
            for p in github.list_prs("all", 50):
                if p["number"] in ours and p["merged"]:
                    event("merged", f"PR #{p['number']} ({ours[p['number']]['service']}) was merged", p["url"], eid=f"merged-{p['number']}")

        if head != built or force:
            event("change", f"Fork {branch} moved to {head[:7]}; re-reading the graph")
            rec = sync.sync_fork(branch)
            _set(last_head=head)
            out.update(synced=True, fixed=len(rec["fixed"]), new=len(rec["new"]))
            event("sync", f"Graph re-read at {head[:7]}: {len(rec['fixed'])} exposures gone, {len(rec['new'])} new")
            for d in rec["decisions"]:
                if d["verified"]:
                    event("verified", f"Verified: {d['text']} (all {d['targets']} targeted findings are gone)", eid=f"verified-{d['decision']}")

            for line in rec["exposure"]["added"]:
                svc = line.split(" via ")[0]
                body = _issue_for_exposure(svc, head)
                a, why = proposals.file_issue(
                    f"{svc} is now reachable from the internet", body, [svc],
                    {"why": f"{svc} gained an internet entry point", "commit": head}, "watcher", f"exposure:{svc}:{head}",
                )
                if a:
                    out["proposals"].append(a["id"])
                    event("proposal", f"Proposed an issue for the owner of {svc}", "/approvals")

            risky = [f for f in rec["new"] if f["kev"] or f["severity"] == "CRITICAL"] + [f for f in rec["worse"] if f["kev"] or f["severity"] == "CRITICAL"]
            if risky or rec["exposure"]["added"]:
                plan = planner.build_plan(5)
                a, why = proposals.file_fix_plan(
                    plan, "watcher",
                    {"why": f"{len(risky)} new or riskier critical/KEV findings after {head[:7]}", "commit": head},
                    f"fixplan:{head}",
                )
                if a:
                    out["proposals"].append(a["id"])
                    event("proposal", f"Proposed a rehearsed fix plan: {plan['summary'].split('.')[0]}", "/approvals")
                elif why and "already waiting" not in why:
                    event("gate", why)
            _set(last_check=_now(), last_status=f"Synced to {head[:7]}")
        else:
            _set(last_check=_now(), last_status=f"Up to date at {head[:7]}")
        out["ms"] = round((time.perf_counter() - t0) * 1000)
        return out
    except Exception as e:
        _set(last_check=_now(), last_status=f"Error: {type(e).__name__}: {str(e)[:120]}")
        return {"ok": False, "status": f"{type(e).__name__}: {e}"}
    finally:
        _lock.release()


async def loop():
    """Background task started with the API. Every INTERVAL seconds, checks each project whose watcher is switched on,
    scoped to that project's graph, repository and checkout."""
    from warden import workspaces

    def check(p: dict):
        with workspaces.scoped(p):
            if state().get("enabled"):
                tick()

    while True:
        await asyncio.sleep(INTERVAL)
        try:
            projects = await asyncio.to_thread(workspaces.ready_projects)
        except Exception as e:
            print(f"watcher loop error: {e}")
            continue
        for p in projects:
            try:
                await asyncio.to_thread(check, p)
            except Exception as e:  # never let the loop die
                print(f"watcher loop error ({p['slug']}): {e}")
