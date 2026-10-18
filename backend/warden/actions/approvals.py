"""Approval gate. Agents and planners *propose* actions as Approval nodes in the shared agents graph
(agents_<tenant>); nothing external happens until a human approves. Approving executes the action and
records a Decision in the org graph, linked to what it changed, so the next question can cite it."""
import json
import time
import uuid

from warden import config, memory
from warden.actions import github
from warden.graph.client import ro, rw


def agents_graph() -> str:
    """Shared agent state for the current project's graph (agents_demo for the demo project)."""
    g = config.org_graph_name()
    return f"agents_{config.TENANT}" if g == f"org_{config.TENANT}" else f"agents_{g}"


def _now() -> int:
    return int(time.time() * 1000)


def _row_to_dict(n) -> dict:
    p = dict(n.properties)
    for k in ("payload_json", "result_json"):
        if k in p and p[k]:
            p[k.replace("_json", "")] = json.loads(p.pop(k))
        else:
            p.pop(k, None)
    return p


def create(kind: str, title: str, summary: str, payload: dict, requested_by: str = "planner") -> dict:
    aid = f"apr_{uuid.uuid4().hex[:10]}"
    rw(
        """CREATE (a:Approval {id: $id, kind: $kind, title: $title, summary: $summary, status: 'pending',
        created_at: $t, requested_by: $by, payload_json: $payload})""",
        {"id": aid, "kind": kind, "title": title, "summary": summary, "t": _now(), "by": requested_by, "payload": json.dumps(payload)},
        agents_graph(),
    )
    return get(aid)


def get(aid: str) -> dict | None:
    rows, _ = ro("MATCH (a:Approval {id: $id}) RETURN a", {"id": aid}, agents_graph())
    return _row_to_dict(rows[0]["a"]) if rows else None


def list_all() -> list[dict]:
    try:
        rows, _ = ro("MATCH (a:Approval) RETURN a ORDER BY a.created_at DESC LIMIT 50", graph_name=agents_graph())
    except Exception as e:  # the agents graph doesn't exist until the first approval is created
        if "Invalid graph operation on empty key" in str(e) or "empty key" in str(e):
            return []
        raise
    items = [_row_to_dict(r["a"]) for r in rows]
    return sorted(items, key=lambda a: (a["status"] != "pending", -a["created_at"]))


def _finish(aid: str, status: str, result: dict, by: str, reason: str | None = None) -> dict:
    rw(
        """MATCH (a:Approval {id: $id}) SET a.status = $status, a.decided_at = $t, a.decided_by = $by,
        a.reason = $reason, a.result_json = $result""",
        {"id": aid, "status": status, "t": _now(), "by": by, "reason": reason, "result": json.dumps(result)},
        agents_graph(),
    )
    return get(aid)


def set_preflight(aid: str, results: list[dict]) -> None:
    """Keeps the pre-flight results on the approval payload so the detail view and the timeline can show them."""
    a = get(aid)
    payload = {**a["payload"], "preflight": {"at": _now(), "steps": results}}
    rw("MATCH (a:Approval {id: $id}) SET a.payload_json = $p", {"id": aid, "p": json.dumps(payload)}, agents_graph())


def reject(aid: str, reason: str, by: str = "you") -> dict:
    a = get(aid)
    if not a or a["status"] != "pending":
        raise ValueError("Only a pending approval can be rejected")
    record_decision(a, "rejected", reason=reason, links=[], by=by)
    return _finish(aid, "rejected", {"executed": False, "reason": reason}, by, reason)


def approve(aid: str, by: str = "you") -> dict:
    a = get(aid)
    if not a or a["status"] != "pending":
        raise ValueError("Only a pending approval can be approved")
    executor = EXECUTORS[a["kind"]]
    if not github.configured():
        result = {"executed": False, "reason": "GitHub fork not configured (GITHUB_TOKEN / GITHUB_OWNER in .env); nothing was sent."}
        record_decision(a, "approved_not_executed", reason=result["reason"], links=[], by=by)
        return _finish(aid, "approved_not_executed", result, by)
    try:
        result = executor(a["payload"])
        result["executed"] = True
    except Exception as e:
        # Keep it pending so the human can fix the cause and approve again; show what went wrong.
        msg = str(e)
        if "410" in msg and a["kind"] == "issue":
            msg = "Issues are turned off on your fork. Enable them in the fork's Settings → General → Features → Issues, then approve again."
        elif "403" in msg:
            msg = "GitHub refused the request: the token is missing a permission (needs Contents, Pull requests and Issues: read and write)."
        else:
            msg = f"{type(e).__name__}: {msg[:240]}"
        rw("MATCH (a:Approval {id: $id}) SET a.last_error = $m, a.last_error_at = $t", {"id": aid, "m": msg, "t": _now()}, agents_graph())
        return get(aid)
    record_decision(a, "approved", reason=None, links=[x["url"] for x in result.get("prs", [])] + ([result["url"]] if result.get("url") else []), by=by)
    return _finish(aid, "approved", result, by)


def record_decision(a: dict, status: str, reason: str | None, links: list[str], by: str | None = None):
    """Decision node in the org graph: what was decided, about which vulnerabilities and services, and where it went."""
    p = a["payload"]
    vulns = sorted({v for it in p.get("items", []) for v in it.get("vulns", [])})
    services = sorted({s for it in p.get("items", []) for s in it.get("services", [])} | set(p.get("services", [])))
    rw(
        """CREATE (d:Decision {id: $id, kind: $kind, text: $text, status: $status, reason: $reason, decided_at: $t,
            approval_id: $aid, links: $links, targets_json: $targets, items_json: $items, ingest_sha: $sha, decided_by: $by, source_type: 'warden'})
        WITH d UNWIND $vulns AS vid MATCH (v:Vulnerability {id: vid}) CREATE (d)-[:ABOUT]->(v)""",
        {"id": f"dec_{uuid.uuid4().hex[:10]}", "kind": a["kind"], "text": a["title"], "status": status, "reason": reason,
         "t": _now(), "aid": a["id"], "links": links, "vulns": vulns,
         # Exactly which (vulnerability, service) findings this decision promised to remove: verification checks these, no more.
         "targets": json.dumps([[r["vuln"], r["service"]] for r in p.get("removed", [])]),
         "items": json.dumps(memory.items_of(p)), "sha": memory.ingest_sha(), "by": by},
    )
    if services:
        rw(
            """MATCH (d:Decision {approval_id: $aid}) WITH d ORDER BY d.decided_at DESC LIMIT 1
            UNWIND $services AS sname MATCH (s:Service {name: sname}) CREATE (d)-[:CHANGES]->(s)""",
            {"aid": a["id"], "services": services},
        )


# ---- executors: one per action kind ----

def _exec_fix_plan(payload: dict) -> dict:
    prs = []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for svc in payload["patches"]:
        files = [{"path": f["path"], "content": f["content"]} for f in svc["files"] if f["changed"]]
        if not files:
            continue
        pkgs = sorted({p for f in svc["files"] for p in f["packages"]})
        body = "\n".join(
            [
                f"Security fix plan for `{svc['service']}`, approved in Warden.",
                "",
                "Upgrades:",
                *[f"- {p}" for p in pkgs],
                "",
                f"Why: {payload['summary']}",
                "",
                f"Rehearsed on a copy of the org graph before opening this PR: reachable findings "
                f"{payload['before']['findings']} → {payload['after']['findings']}, CISA KEV findings "
                f"{payload['before']['kev_findings']} → {payload['after']['kev_findings']}.",
                "",
                "Lockfiles are not regenerated here: run `go mod tidy` / `npm install` in CI before merging.",
            ]
        )
        prs.append(
            {"service": svc["service"], **github.open_pr(f"warden/fix-{svc['service']}-{stamp}", files, f"Security upgrades for {svc['service']}", body)}
        )
    return {"prs": prs}


def _exec_pr_comment(payload: dict) -> dict:
    """Posts the impact report on the fork PR, labels its risk, and requests reviewers from the owning teams
    (fork collaborators listed in teams.yaml only; real upstream people are never requested or mentioned)."""
    n = payload["pr"]
    c = github.comment(n, payload["comment"])
    github.add_labels(n, [f"risk: {payload['risk']}"])
    req = github.request_reviewers(n, payload.get("reviewers", []))
    return {"url": c["url"], "labels": [f"risk: {payload['risk']}"], "reviewers": req["requested"]}


def _exec_issue(payload: dict) -> dict:
    i = github.open_issue(payload["title"], payload["body"], payload.get("labels"))
    return {"url": i["url"], "number": i["number"]}


EXECUTORS = {"fix_plan": _exec_fix_plan, "pr_comment": _exec_pr_comment, "issue": _exec_issue}
