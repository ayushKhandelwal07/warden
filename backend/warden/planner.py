"""Remediation planner: the graph decides which upgrades remove the most attack-path risk, then proves it.

1. Score every internet-reachable (vulnerability, service, package) path (same risk model as reachable_findings).
2. Candidates = one upgrade per vulnerable package version, to the lowest version that fixes all its known
   advisories, applied in every service that ships it.
3. Greedy set cover by risk removed. Paths on the CISA KEV list are always covered first.
4. Rehearsal: copy the live graph (GRAPH.COPY), apply the upgrades to the copy, load the *new* versions'
   advisories from OSV, and re-run reachability. Before/after numbers are measured, not estimated.
   The copy is always deleted.
"""
import time
import uuid

from warden import config
from warden.graph.client import copy_graph, delete_graph, unwind
from warden.ingest import intel, load, osv
from warden.ingest.common import version_key
from warden.tools.base import Trace
from warden.tools.security import best_findings, scored_paths


def _target_version(ecosystem: str, name: str, fixed: str) -> str:
    """OSV gives Go module fixes without the 'v'; our package keys keep the manifest's spelling."""
    if ecosystem == "Go" and name != "stdlib" and not fixed.startswith("v"):
        return "v" + fixed
    return fixed


def _candidates(paths: list[dict]) -> list[dict]:
    by_pkg: dict[str, dict] = {}
    for p in paths:
        c = by_pkg.setdefault(
            p["package_key"],
            {"package_key": p["package_key"], "package": p["package_name"], "ecosystem": p["ecosystem"],
             "from": p["version"], "fixes": set(), "paths": []},
        )
        c["paths"].append(p)
        if p["fixed"]:
            c["fixes"].add(p["fixed"])
    out = []
    for c in by_pkg.values():
        if not c["fixes"]:
            continue  # no published fix: nothing to propose
        to = max(c["fixes"], key=version_key)
        removable = [p for p in c["paths"] if p["fixed"] and version_key(p["fixed"]) <= version_key(to)]
        out.append({**c, "to": to, "to_version": _target_version(c["ecosystem"], c["package"], to), "removable": removable})
    return out


def choose(paths: list[dict], max_fixes: int) -> list[dict]:
    cands = _candidates(paths)
    covered: set[tuple] = set()
    chosen: list[dict] = []

    def gain(c):
        return sum(p["risk"] for p in c["removable"] if (p["vuln"], p["service"], p["package_key"]) not in covered)

    def take(c, reason):
        chosen.append({**c, "reason": reason, "risk_removed": round(gain(c), 1)})
        covered.update((p["vuln"], p["service"], p["package_key"]) for p in c["removable"])

    for c in sorted((c for c in cands if any(p["kev"] for p in c["removable"])), key=gain, reverse=True):
        if len(chosen) < max_fixes and gain(c) > 0:
            take(c, "covers a CISA KEV path (policy POL-KEV-48H)")
    while len(chosen) < max_fixes:
        rest = [c for c in cands if c["package_key"] not in {x["package_key"] for x in chosen} and gain(c) > 0]
        if not rest:
            break
        best = max(rest, key=gain)
        take(best, "largest remaining risk removed")
    return chosen


def _summary_numbers(paths: list[dict]) -> dict:
    findings = best_findings(paths)
    return {
        "findings": len(findings),
        "vulnerabilities": len({f["vuln"] for f in findings}),
        "kev_findings": sum(1 for f in findings if f["kev"]),
        "risk": round(sum(f["risk"] for f in findings), 1),
        "keys": {(f["vuln"], f["service"]) for f in findings},
        "by_key": {(f["vuln"], f["service"]): f for f in findings},
    }


def rehearse(chosen: list[dict], graph_name: str | None = None) -> dict:
    live = graph_name or config.org_graph_name()
    copy = f"{live}_rehearsal_{uuid.uuid4().hex[:8]}"
    t0 = time.perf_counter()
    copy_graph(live, copy)
    try:
        new_pkgs = [
            {"key": f"{c['ecosystem']}:{c['package']}@{c['to_version']}", "name": c["package"], "version": c["to_version"], "ecosystem": c["ecosystem"]}
            for c in chosen
        ]
        unwind("MERGE (p:Package {key: row.key}) SET p.name = row.name, p.version = row.version, p.ecosystem = row.ecosystem, p.rehearsal = true", new_pkgs, copy)
        swaps = [{"old": c["package_key"], "new": n["key"]} for c, n in zip(chosen, new_pkgs)]
        unwind(
            """MATCH (s:Service)-[d:DEPENDS_ON]->(:Package {key: row.old}), (np:Package {key: row.new})
            CREATE (s)-[:DEPENDS_ON {direct: d.direct, manifest: d.manifest, source_type: 'rehearsal'}]->(np)
            DELETE d""",
            swaps,
            copy,
        )
        # The upgraded versions are checked against OSV too: an upgrade can still carry other advisories.
        fresh = osv.fetch_vulnerabilities(new_pkgs)
        intel.enrich(fresh["vulns"], use_nvd=False)
        load.load_vulnerabilities(fresh, run=0, g=copy)
        after_paths = scored_paths(Trace(), graph_name=copy)
        new_advisories = sorted({a["vuln"] for a in fresh["affected"]})
    finally:
        delete_graph(copy)
    return {"graph": copy, "after_paths": after_paths, "new_advisories": new_advisories, "ms": round((time.perf_counter() - t0) * 1000)}


def _gate(before: dict, after: dict, added: list[tuple]) -> dict:
    """Rehearsal gate: a fix is only proposed if the graph copy *proves* it helps and breaks nothing new."""
    new_bad = [(v, s) for v, s in added if after["by_key"][(v, s)]["kev"] or after["by_key"][(v, s)]["severity"] == "CRITICAL"]
    checks = [
        {"check": "total risk drops", "ok": after["risk"] < before["risk"], "detail": f"{round(before['risk'])} → {round(after['risk'])}"},
        {"check": "KEV findings eliminated or reduced", "ok": after["kev_findings"] == 0 or after["kev_findings"] < before["kev_findings"],
         "detail": f"{before['kev_findings']} → {after['kev_findings']}"},
        {"check": "no new critical or KEV finding", "ok": not new_bad, "detail": ", ".join(f"{v} on {s}" for v, s in new_bad) or "none"},
    ]
    return {"passed": all(c["ok"] for c in checks), "checks": checks}


def build_plan(max_fixes: int = 5, graph_name: str | None = None) -> dict:
    trace = Trace()
    before_paths = scored_paths(trace, graph_name=graph_name)
    chosen = choose(before_paths, max_fixes)
    if not chosen:
        return {"items": [], "summary": "No reachable vulnerability has a published fix: there is nothing to upgrade.", "before": None, "after": None}
    reh = rehearse(chosen, graph_name)
    before, after = _summary_numbers(before_paths), _summary_numbers(reh["after_paths"])
    removed = sorted(before["keys"] - after["keys"])
    added = sorted(after["keys"] - before["keys"])
    owners = {
        r["service"]: r["team"]
        for r in trace.ro("MATCH (s:Service)-[:OWNED_BY]->(t:Team) RETURN s.name AS service, t.name AS team", graph_name=graph_name)
    }
    items = []
    for c in chosen:
        services = sorted({p["service"] for p in c["removable"]})
        items.append(
            {
                "package": c["package"], "ecosystem": c["ecosystem"], "from": c["from"], "to": c["to_version"],
                "services": services, "owners": sorted({owners.get(s, "unowned") for s in services}),
                "vulns": sorted({p["vuln"] for p in c["removable"]}), "kev": any(p["kev"] for p in c["removable"]),
                "risk_removed": c["risk_removed"], "reason": c["reason"],
                "changes": sorted({(p["service"], p["manifest"], p["direct"]) for p in c["removable"]}),
            }
        )
    gate = _gate(before, after, added)
    pct = 0 if not before["risk"] else round(100 * (before["risk"] - after["risk"]) / before["risk"])
    kev_left = after["kev_findings"]
    summary = (
        f"{len(items)} upgrade{'s' if len(items) != 1 else ''} remove {len(removed)} of {before['findings']} reachable findings "
        f"({pct}% of total risk){', including every CISA KEV path' if before['kev_findings'] and not kev_left else ''}. "
        f"Measured by rehearsing on a copy of the graph, not estimated."
    )
    strip = lambda d: {k: v for k, v in d.items() if k not in ("keys", "by_key")}  # noqa: E731
    return {
        "summary": summary,
        "gate": gate,
        "items": items,
        "before": strip(before),
        "after": strip(after),
        "removed": [{"vuln": v, "service": s, "risk": before["by_key"][(v, s)]["risk"]} for v, s in removed],
        "added": [{"vuln": v, "service": s} for v, s in added],
        "new_advisories_on_upgraded_versions": reh["new_advisories"],
        "rehearsal": {"graph": reh["graph"], "ms": reh["ms"], "deleted": True},
        "queries": trace.queries,
    }
