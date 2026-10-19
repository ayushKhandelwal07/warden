"""Closed loop: keep the graph current, see what changed, and check that approved fixes actually landed.

    sync(ref)      snapshot live -> org_<t>_prev, re-ingest at `ref`, diff prev vs live, verify Decisions
    what_if(svc)   rehearse "this service becomes internet-facing" on a GRAPH.COPY and diff it
    reset()        golden snapshot -> live, clear agent state, repo back to the ref the graph was built from
"""
import json
import time
import uuid

from warden import config
from warden import timeline
from warden.actions import approvals
from warden.graph.client import copy_graph, delete_graph, graph_exists, ro, rw
from warden.ingest import repo
from warden.ingest.pipeline import run as ingest
from warden.tools.base import Trace
from warden.tools.security import best_findings, scored_paths


def prev_graph() -> str:
    return f"{config.org_graph_name()}_prev"


def current_ref() -> dict:
    rows, _ = ro("MATCH (r:IngestRun) RETURN r.ref AS ref, r.sha AS sha, r.at AS at ORDER BY r.at DESC LIMIT 1")
    return rows[0] if rows else {}


def available_refs() -> list[str]:
    """What the graph can be re-read at. The demo: microservices-demo releases from the pinned one on. Another repo:
    the branch it was built from, then its newest tags."""
    if config.is_demo_source():
        tags = [t for t in repo.git("tag", "--sort=creatordate").split() if t.startswith("v0.") and t.count(".") == 2]
        start = tags.index(config.DEMO_REF) if config.DEMO_REF in tags else 0
        return tags[start:]
    tags = repo.git("tag", "--sort=-creatordate").split()[:10]
    return [config.source_ref(), *[t for t in tags if t != config.source_ref()]]


def _findings(graph_name: str) -> dict:
    return {(f["vuln"], f["service"]): f for f in best_findings(scored_paths(Trace(), graph_name=graph_name))}


def _edges(graph_name: str, rel: str, a: str, b: str) -> set[tuple]:
    rows, _ = ro(f"MATCH (x:{a})-[:{rel}]->(y:{b}) RETURN x.name AS x, coalesce(y.key, y.name) AS y", graph_name=graph_name)
    return {(r["x"], r["y"]) for r in rows}


def _version_changes(dep_b: set[tuple], dep_a: set[tuple]) -> dict:
    """(service, 'eco:name@version') edges -> per-package version moves, additions and removals."""
    def split(key):
        name, _, ver = key.rpartition("@")
        return name.split(":", 1)[1], ver

    vb: dict[tuple, set] = {}
    va: dict[tuple, set] = {}
    for svc, key in dep_b:
        n, v = split(key)
        vb.setdefault((svc, n), set()).add(v)
    for svc, key in dep_a:
        n, v = split(key)
        va.setdefault((svc, n), set()).add(v)
    moved: dict[str, dict] = {}
    for k in set(vb) & set(va):
        if vb[k] != va[k]:
            label = f"{k[1]} {'/'.join(sorted(vb[k])).lstrip('v')} → {'/'.join(sorted(va[k])).lstrip('v')}"
            moved.setdefault(label, {"change": label, "services": []})["services"].append(k[0])
    return {
        "changed": len({k for k in set(vb) & set(va) if vb[k] != va[k]}),
        "added": len(set(va) - set(vb)),
        "removed": len(set(vb) - set(va)),
        "moves": sorted(moved.values(), key=lambda m: (-len(m["services"]), m["change"]))[:25],
    }


def diff_graphs(before: str, after: str) -> dict:
    fb, fa = _findings(before), _findings(after)
    fixed = sorted(set(fb) - set(fa))
    new = sorted(set(fa) - set(fb))
    dep_b, dep_a = _edges(before, "DEPENDS_ON", "Service", "Package"), _edges(after, "DEPENDS_ON", "Service", "Package")
    exp_b, exp_a = _edges(before, "EXPOSED_VIA", "Service", "Ingress"), _edges(after, "EXPOSED_VIA", "Service", "Ingress")
    call_b, call_a = _edges(before, "CALLS", "Service", "Service"), _edges(after, "CALLS", "Service", "Service")

    def risk(fs):
        return round(sum(f["risk"] for f in fs.values()), 1)

    def row(f):
        return {"vuln": f["vuln"], "service": f["service"], "kev": f["kev"], "severity": f["severity"], "package": f["package"],
                "hops": f["hops"], "risk": f["risk"]}

    return {
        "before": {"findings": len(fb), "kev_findings": sum(f["kev"] for f in fb.values()), "risk": risk(fb)},
        "after": {"findings": len(fa), "kev_findings": sum(f["kev"] for f in fa.values()), "risk": risk(fa)},
        "fixed": sorted((row(fb[k]) for k in fixed), key=lambda r: -r["risk"]),
        # Same finding, different exposure: fewer hops from the internet means more risk.
        "worse": sorted(
            ({**row(fa[k]), "hops_before": fb[k]["hops"], "risk_before": fb[k]["risk"]} for k in set(fa) & set(fb) if fa[k]["hops"] < fb[k]["hops"]),
            key=lambda r: -(r["risk"] - r["risk_before"]),
        )[:50],
        "new": sorted((row(fa[k]) for k in new), key=lambda r: -r["risk"]),
        "dependencies": _version_changes(dep_b, dep_a),
        "exposure": {"added": sorted(f"{x} via {y}" for x, y in exp_a - exp_b), "removed": sorted(f"{x} via {y}" for x, y in exp_b - exp_a)},
        "calls": {"added": sorted(f"{x} → {y}" for x, y in call_a - call_b), "removed": sorted(f"{x} → {y}" for x, y in call_b - call_a)},
    }


def verify_decisions(diff: dict) -> list[dict]:
    """An approved fix is verified once none of the findings it promised to remove is reachable any more.
    Targets are the exact (vulnerability, service) pairs stored on the decision when it was approved."""
    still = {(f["vuln"], f["service"]) for f in _findings(config.org_graph_name()).values()}
    rows, _ = ro(
        """MATCH (d:Decision) WHERE d.status IN ['approved', 'approved_not_executed'] AND d.targets_json IS NOT NULL
        RETURN d.id AS id, d.text AS text, d.targets_json AS targets"""
    )
    out = []
    for d in rows:
        targets = {tuple(t) for t in json.loads(d["targets"] or "[]")}
        if not targets:
            continue
        remaining = targets & still
        verified = not remaining
        if verified:
            rw("MATCH (d:Decision {id: $id}) SET d.status = 'verified', d.verified_at = timestamp()", {"id": d["id"]})
        out.append({"decision": d["id"], "text": d["text"], "verified": verified, "remaining": len(remaining), "targets": len(targets),
                    "done_pct": round(100 * (len(targets) - len(remaining)) / len(targets))})
    return out


def sync(ref: str) -> dict:
    t0 = time.perf_counter()
    before_ref = current_ref()
    copy_graph(config.org_graph_name(), prev_graph())
    res = ingest(ref, fetch=True, use_nvd=False, quiet=True)
    diff = diff_graphs(prev_graph(), config.org_graph_name())
    decisions = verify_decisions(diff)
    timeline.record(diff, ref, res["sha"])
    record = {
        "id": f"sync_{uuid.uuid4().hex[:8]}", "from_ref": before_ref.get("ref"), "from_sha": before_ref.get("sha"),
        "to_ref": ref, "to_sha": res["sha"], "ms": round((time.perf_counter() - t0) * 1000), **diff, "decisions": decisions,
    }
    rw(
        "CREATE (s:SyncRun {id: $id, at: timestamp(), from_ref: $f, to_ref: $t, summary_json: $j})",
        {"id": record["id"], "f": record["from_ref"], "t": ref, "j": json.dumps(record)},
        approvals.agents_graph(),
    )
    return record


def sync_fork(branch: str) -> dict:
    """Re-read the graph from the branch the project acts on (for the demo: the fork's branch, not upstream)."""
    return sync(repo.fetch_fork(branch))


def what_if_expose(service: str) -> dict:
    """Rehearsal: what new attack paths appear if `service` gets a public LoadBalancer?"""
    copy = f"{config.org_graph_name()}_whatif_{uuid.uuid4().hex[:8]}"
    copy_graph(config.org_graph_name(), copy)
    try:
        rows, _ = ro("MATCH (s:Service {name: $s}) RETURN s.name AS n", {"s": service}, copy)
        if not rows:
            raise ValueError(f"Service '{service}' is not in the graph")
        rw(
            """MATCH (s:Service {name: $s}), (net:Internet)
            MERGE (i:Ingress {name: $ing}) SET i.kind = 'LoadBalancer', i.what_if = true
            MERGE (s)-[:EXPOSED_VIA]->(i) MERGE (net)-[:REACHES]->(i)""",
            {"s": service, "ing": f"{service}-external"},
            copy,
        )
        diff = diff_graphs(config.org_graph_name(), copy)
    finally:
        delete_graph(copy)
    return {"service": service, "graph": copy, "deleted": True, **diff}


def history() -> list[dict]:
    if approvals.agents_graph() not in __import__("warden.graph.client", fromlist=["db"]).db().list_graphs():
        return []
    rows, _ = ro("MATCH (s:SyncRun) RETURN s.summary_json AS j ORDER BY s.at DESC LIMIT 10", graph_name=approvals.agents_graph())
    return [json.loads(r["j"]) for r in rows]


def reset() -> dict:
    """Back to the clean state: golden graph, no agent state, repo at the ref the graph was first built from."""
    if not graph_exists(config.golden_graph_name()):
        raise RuntimeError("No golden snapshot; run `python -m warden.ingest --snapshot` first")
    copy_graph(config.golden_graph_name(), config.org_graph_name())
    delete_graph(approvals.agents_graph())
    delete_graph(prev_graph())
    repo.ensure_repo(config.source_ref())
    return {"reset": True, **current_ref()}
