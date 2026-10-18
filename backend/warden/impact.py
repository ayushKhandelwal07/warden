"""PR impact analysis: what a change can break, what went wrong before, and who should review it.

Orchestrates the graph tools (the same ones the agent and MCP clients call) and keeps every tool
result, so the report shows its evidence. Works on merged PRs from the ingested history, or on open
PRs of the fork (files fetched from GitHub), which is where the report can be posted as a comment.
"""
import re

from warden.actions import github
from warden.graph.evidence import Evidence
from warden.ingest.history import file_service
from warden.tools import run_tool
from warden.tools.base import ToolError, Trace

DEP_FILES = ("go.mod", "go.sum", "package.json", "package-lock.json", "requirements.txt", "requirements.in", ".csproj", "build.gradle")
TITLE_PKG = re.compile(r"(?:update|bump|upgrade)\s+(?:module|dependency|dependencies)?\s*([\w./@:\-]+)(?:\s+monorepo)?\s+(?:to|from)\b", re.I)


def _change_kind(title: str, files: list[str]) -> tuple[str, str | None]:
    m = TITLE_PKG.search(title or "")
    pkg = m.group(1) if m else None
    if "health" in (title or "").lower():
        return "config", "health-check"
    if any(f.endswith("Dockerfile") for f in files) and (not pkg or "node" in (pkg or "") or "image" in title.lower()):
        return "base-image", pkg or ("node" if "node" in title.lower() else None)
    if any(f.endswith(DEP_FILES) or f.split("/")[-1] in DEP_FILES for f in files) or pkg:
        return "dependency-bump", pkg
    if any("health" in f.lower() or "manifest" in f.lower() or f.endswith(".yaml") for f in files):
        return "config", "health-check" if "health" in title.lower() else None
    return "code", None


def _services_from_files(files: list[str]) -> dict[str, list[str]]:
    rows = Trace().ro("MATCH (s:Service) RETURN s.name AS name")
    names = {r["name"] for r in rows}
    out: dict[str, list[str]] = {}
    for f in files:
        s = file_service(f, names)
        if s:
            out.setdefault(s, []).append(f)
    return out


def analyze(number: int, source: str = "history") -> dict:
    calls: list[dict] = []

    def call(name, **args):
        r = run_tool(name, args)
        calls.append(r)
        return r

    if source == "fork":
        pr = github.get_pr(number)
        title, url, author, files = pr["title"], pr["url"], pr["author"], pr["files"]
        touched = _services_from_files(files)
    else:
        t = call("pr_touched_services", pr=number)
        if t["error"]:
            raise ToolError(t["error"])
        head = Trace().ro(
            """MATCH (pr:PullRequest {number: $n})-[:CONTAINS]->(:Commit)-[:TOUCHES]->(f:File)
RETURN pr.title AS title, pr.url AS url, collect(DISTINCT f.path) AS files""",
            {"n": number},
        )[0]
        title, url, author, files = head["title"], head["url"], None, head["files"]
        touched = _services_from_files(files)
    services = sorted(touched)
    kind, pkg = _change_kind(title, files)

    if not services:
        return {"pr": number, "source": source, "title": title, "url": url, "services": [], "risk": {"label": "low", "why": ["touches no service code"]},
                "summary": f"PR #{number} touches no service code, so it has no service blast radius.", "calls": calls}

    shallow, deep = {}, {}
    for s in services:
        for r in call("blast_radius", service=s, depth=1)["rows"]:
            shallow.setdefault(r["service"], r)
        for r in call("blast_radius", service=s, depth=3)["rows"]:
            if r["service"] not in deep or r["hops"] < deep[r["service"]]["hops"]:
                deep[r["service"]] = r
    for s in services:  # a touched service isn't its own dependent
        shallow.pop(s, None)
        deep.pop(s, None)
    hidden = sorted(set(deep) - set(shallow))

    choke_rows = call("rank", algorithm="betweenness")["rows"]
    chokepoints = [r["service"] for r in choke_rows[:3] if r["score"] > 0 and r["service"] in services]

    inc = call("past_incidents", services=services + sorted(deep), package=pkg or "")
    # Only incidents on the services this PR changes count as "the same change went wrong before".
    same_kind = [r for r in inc["rows"] if r["same_kind_of_change"] and set(r["affected_here"].split(", ")) & set(services)]

    owners, reviewers = {}, []
    for s in services:
        o = call("who_owns", service=s)
        if o["rows"]:
            owners[s] = o["rows"][0]["team"]
        for r in call("who_knows", service=s, limit=3)["rows"]:
            if r["person"] not in [x["person"] for x in reviewers] and not (author and r["login"] == author):
                reviewers.append({**r, "service": s})

    policies = []
    for s in services:
        for r in call("policies_for", service=s)["rows"]:
            if r["applies"] and r["policy"] not in [p["policy"] for p in policies]:
                policies.append(r)

    # Risk = points from graph facts, each one stated, so the label explains itself.
    points: list[tuple[int, str]] = []
    if any(p["policy"] == "POL-PCI-REVIEW" for p in policies):
        points.append((2, "touches a service that reads card data (POL-PCI-REVIEW)"))
    if same_kind:
        sev = same_kind[0]["severity"]
        points.append((2 if sev == "SEV1" else 1, f"the same kind of change caused {same_kind[0]['incident']} ({sev})"))
    if chokepoints:
        points.append((1, f"changes a choke point ({', '.join(chokepoints)}; betweenness)"))
    if "frontend" in services:
        points.append((1, "changes the internet-facing frontend directly"))
    elif hidden_public := sorted(s for s in hidden if deep[s]["internet_facing"]):
        points.append((1, f"reaches internet-facing {', '.join(hidden_public)} only through other services (depth > 1)"))
    if len(services) >= 4:
        points.append((1, f"spans {len(services)} services"))
    score = sum(p for p, _ in points)
    label = "high" if score >= 4 else "medium" if score >= 2 else "low"
    why = [w for _, w in points] or ["no sensitive data, choke points, matching incidents or internet exposure in the graph"]

    ev = Evidence()
    for c in calls:
        if c["tool"] in ("blast_radius",) and c["args"].get("depth") == 3 and c["evidence"]:
            for n in c["evidence"]["nodes"]:
                ev.nodes.setdefault(n["id"], n)
            for e in c["evidence"]["edges"]:
                ev.edges.setdefault(e["id"], e)

    summary = (
        f"PR #{number} ({kind}{f' of {pkg}' if pkg else ''}) touches {', '.join(services)}. "
        f"Depth 1: {len(shallow)} dependent(s); depth 3: {len(deep)}"
        + (f", revealing {', '.join(hidden)}" if hidden else "")
        + f". Risk: {label.upper()}, because it {'; '.join(why)}."
    )
    report = {
        "pr": number, "source": source, "title": title, "url": url, "author": author, "kind": kind, "package": pkg,
        "services": [{"service": s, "files": touched[s], "owner": owners.get(s)} for s in services],
        "depth1": sorted(shallow.values(), key=lambda r: (r["hops"], r["service"])),
        "depth3": sorted(deep.values(), key=lambda r: (r["hops"], r["service"])),
        "hidden": hidden, "chokepoints": chokepoints, "incidents": inc["rows"], "reviewers": reviewers[:4],
        "policies": policies, "risk": {"label": label, "score": score, "why": why}, "summary": summary,
        "evidence": ev.to_json(), "calls": calls,
    }
    report["comment"] = render_comment(report)
    return report


def render_comment(r: dict) -> str:
    """GitHub comment body. Plain names only (no @): nobody gets pinged by a report."""
    lines = [f"### Warden impact report: risk **{r['risk']['label'].upper()}**", "", r["summary"], ""]
    affected = [
        f"- {d['service']}: {d['hops']} hop(s){' (internet-facing)' if d['internet_facing'] else ''}{' (only visible at depth 3)' if d['service'] in r['hidden'] else ''}"
        for d in r["depth3"]
    ]
    lines += ["**Affected services**"] + (affected or ["- none"])
    if r["incidents"]:
        lines += ["", "**Past incidents on these services**"] + [
            f"- {i['incident']} ({i['severity']}, {i['date']}): {i['title']}{' (same kind of change)' if i['same_kind_of_change'] else ''}"
            for i in r["incidents"][:3]
        ]
    if r["policies"]:
        lines += ["", "**Policies**"] + [f"- {p['policy']}: {p['rule']}" for p in r["policies"]]
    if r["reviewers"]:
        lines += ["", "**Suggested reviewers (from commit history)**"] + [
            f"- {x['person']}: {x['commits']} commits on {x['service']}, last {x['last_touched']}" for x in r["reviewers"]
        ]
    lines += ["", "_Every line above comes from a path in the org graph (FalkorDB). Incident history is curated and synthetic._"]
    return "\n".join(lines)
