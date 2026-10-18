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

from warden import config, contradictions, memory, regression
from warden.actions import patches
from warden.graph.evidence import Evidence
from warden.graph.client import copy_graph, delete_graph, unwind
from warden.ingest import intel, load, osv
from warden.ingest.common import version_key
from warden.tools.base import Trace
from warden.tools.security import FINDING_PATH_CYPHER, _attach_context, best_findings, scored_paths


# The same service on the upgraded package (the advisory edge is gone once the fix works).
UPGRADED_PATH_CYPHER = """
MATCH p = (:Internet)-[:REACHES]->(:Ingress)<-[:EXPOSED_VIA]-(:Service)-[:CALLS*0..4]->(s:Service {name: $service})
      -[:DEPENDS_ON]->(:Package {key: $key})
RETURN p ORDER BY length(p) ASC LIMIT 1"""


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


def rehearse(chosen: list[dict], graph_name: str | None = None, probe=None) -> dict:
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
        probed = probe(copy, after_paths) if probe else None  # read from the copy before it is deleted
    finally:
        delete_graph(copy)
    return {"graph": copy, "after_paths": after_paths, "new_advisories": new_advisories, "probe": probed, "ms": round((time.perf_counter() - t0) * 1000)}


def _check(name: str, ok: bool, detail: str, level: str = "block") -> dict:
    """level: block = a failure stops the plan · warn = needs a human's attention · info = shown for context."""
    return {"check": name, "ok": ok, "detail": detail, "level": level}


def _gate(before: dict, after: dict, added: list[tuple], reg: dict | None = None, items: list[dict] | None = None, conflicts: list[dict] | None = None) -> dict:
    """Deterministic gate: a fix is only proposed if the graph copy *proves* it helps and creates no new exposure.
    No language model is involved; the LLM cannot talk its way past this."""
    empty = {"before": 0, "after": 0, "removed": [], "remaining": [], "new": []}
    reg = reg or {"kev": empty, "sensitive": empty, "data": empty}
    items = items or []
    new_bad = [(v, s) for v, s in added if after["by_key"][(v, s)]["kev"] or after["by_key"][(v, s)]["severity"] == "CRITICAL"]
    kev, sens, data = reg["kev"], reg["sensitive"], reg["data"]
    new_services = sorted({s for _, s in after.get("keys", set())} - {s for _, s in before.get("keys", set())})
    majors = [f"{i['package']} {i['from']} → {i['to']}" for i in items if patches.major_bump(i["from"], i["to"])]
    serious_new = [r for r in sens["new"] if r["severity"] in ("HIGH", "CRITICAL") or r["kev"] or r["tier"] == "exploit_signal"]
    minor_new = [r for r in sens["new"] if r not in serious_new]
    left = sorted(after.get("by_key", {}).values(), key=lambda f: -f.get("risk", 0))[:3]
    checks = [
        _check("no open evidence contradiction on what this plan touches", not conflicts,
               "; ".join(c["detail"] for c in (conflicts or [])[:3]) or "none"),
        _check("total risk drops", after["risk"] < before["risk"], f"{round(before['risk'])} → {round(after['risk'])}"),
        _check("KEV exposures eliminated or reduced", after["kev_findings"] == 0 or after["kev_findings"] < before["kev_findings"],
               f"{before['kev_findings']} → {after['kev_findings']} ({len(kev['removed'])} of {kev['before']} removed)"),
        _check("no new critical or KEV exposure", not new_bad, ", ".join(f"{v} on {s}" for v, s in new_bad) or "none"),
        _check("no new high-severity or exploit-signal exposure of PCI/PII data", not serious_new,
               ", ".join(f"{r['vuln']} in {r['service']} ({r['severity']})" for r in serious_new) or f"{len(data['remaining'])} service-data pairs stay exposed, none added"),
        _check("no service newly exposed to a vulnerability", not new_services, ", ".join(new_services) or "none"),
        _check("no new lower-severity exposure of PCI/PII data", not minor_new,
               ", ".join(f"{r['vuln']} in {r['service']} ({r['severity']})" for r in minor_new) or "none", level="warn"),
        _check("no major-version jump", not majors, "; ".join(majors) or "none", level="warn"),
        _check("residual KEV exposure", not kev["remaining"], ", ".join(f"{r['vuln']} in {r['service']}" for r in kev["remaining"]) or "none", level="warn"),
        _check("highest remaining exposures", True, "; ".join(f"{f.get('vuln', '?')} in {f.get('service', '?')} (risk {f.get('risk', 0)})" for f in left) or "none", level="info"),
    ]
    return {"passed": all(c["ok"] for c in checks if c["level"] == "block"), "checks": checks}


def build_plan(max_fixes: int = 5, graph_name: str | None = None, chosen_override: list[dict] | None = None) -> dict:
    trace = Trace()
    before_paths = scored_paths(trace, graph_name=graph_name)
    mem = None
    if chosen_override is not None:
        chosen = chosen_override
    else:
        usual = choose(before_paths, max_fixes)
        kept, notes = memory.adjust_candidates(before_paths, memory.ingest_sha())
        chosen = choose(kept, max_fixes) if len(kept) != len(before_paths) else usual
        names = lambda cs: sorted({c["package"] for c in cs})  # noqa: E731
        mem = {"notes": notes, "changed": {"from": names(usual), "to": names(chosen)} if names(usual) != names(chosen) else None}
    if not chosen:
        return {"items": [], "summary": "No reachable vulnerability has a published fix: there is nothing to upgrade.", "before": None, "after": None}
    before_findings = best_findings(before_paths)
    assets = regression.sensitive_assets(trace, graph_name)
    hero = next((f for f in before_findings if f["kev"]), before_findings[0] if before_findings else None)
    hero_item = next((c for c in chosen if hero and any(p["vuln"] == hero["vuln"] and p["service"] == hero["service"] for p in c["removable"])), None)

    def probe(copy, after_paths):
        # The headline path in the rehearsal copy: the same service, now on the upgraded package.
        if not hero_item:
            return None
        key = f"{hero_item['ecosystem']}:{hero_item['package']}@{hero_item['to_version']}"
        rows = Trace().ro(UPGRADED_PATH_CYPHER, {"service": hero["service"], "key": key}, copy)
        still = (hero["vuln"], hero["service"]) in {(f["vuln"], f["service"]) for f in best_findings(after_paths)}
        return {"after_evidence": Evidence().add_path(rows[0]["p"]).to_json() if rows else None, "still_exposed": still, "package_after": key}

    reh = rehearse(chosen, graph_name, probe)
    before, after = _summary_numbers(before_paths), _summary_numbers(reh["after_paths"])
    reg = regression.classify(regression.invariants(before_findings, assets), regression.invariants(best_findings(reh["after_paths"]), assets))
    proof = None
    if hero_item:
        prow = trace.ro(FINDING_PATH_CYPHER, {"service": hero["service"], "package_key": hero["package_key"], "vuln": hero["vuln"]}, graph_name)
        if prow:
            ev = Evidence().add_path(prow[0]["p"])
            _attach_context(trace, ev, hero["vuln"], hero["service"], len(prow[0]["p"].nodes()) - 1, graph_name)
            pr = reh["probe"] or {}
            proof = {"vuln": hero["vuln"], "service": hero["service"], "kev": hero["kev"], "package_before": hero["package"], "package_after": pr.get("package_after"),
                     "before": ev.to_json(), "after": pr.get("after_evidence"), "removed": not pr.get("still_exposed", True)}
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
    conflicts = contradictions.blocking(items, graph_name)
    gate = _gate(before, after, added, reg, items, conflicts)
    pct = 0 if not before["risk"] else round(100 * (before["risk"] - after["risk"]) / before["risk"])
    kev_left = after["kev_findings"]
    summary = (
        f"{len(items)} upgrade{'s' if len(items) != 1 else ''} remove {len(removed)} of {before['findings']} graph-reachable exposures (advisory × service) "
        f"({pct}% of total risk){', including every CISA KEV path' if before['kev_findings'] and not kev_left else ''}. "
        f"Measured by rehearsing on a copy of the graph, not estimated."
    )
    strip = lambda d: {k: v for k, v in d.items() if k not in ("keys", "by_key")}  # noqa: E731
    return {
        "summary": summary,
        "gate": gate,
        "regression": reg,
        "proof": proof,
        "items": items,
        "before": strip(before),
        "after": strip(after),
        "removed": [{"vuln": v, "service": s, "risk": before["by_key"][(v, s)]["risk"]} for v, s in removed],
        "added": [{"vuln": v, "service": s} for v, s in added],
        "new_advisories_on_upgraded_versions": reh["new_advisories"],
        "rehearsal": {"graph": reh["graph"], "ms": reh["ms"], "deleted": True},
        "memory": mem,
        "contradictions": conflicts,
        "queries": trace.queries,
    }


UNSAFE_PIN = "v0.9.0"


def unsafe_demo(graph_name: str | None = None) -> dict:
    """A deliberately bad plan, rehearsed for real: pin the KEV-affected golang.org/x/net to an older release.
    It exists to show the deterministic gate blocking a fix that does not remove the path (and may add exposure)."""
    paths = scored_paths(Trace(), graph_name=graph_name)
    kev = next((p for p in best_findings(paths) if p["kev"]), None)
    if not kev:
        return {"items": [], "summary": "No KEV exposure to demonstrate with.", "gate": {"passed": True, "checks": []}}
    bad = {"package_key": kev["package_key"], "package": kev["package_name"], "ecosystem": kev["ecosystem"], "from": kev["version"],
           "to": UNSAFE_PIN, "to_version": UNSAFE_PIN, "removable": [], "fixes": set(), "paths": [kev],
           "reason": "Deliberately unsafe: pins to an older release that still carries the advisory", "risk_removed": 0.0}
    plan = build_plan(1, graph_name, chosen_override=[bad])
    plan["unsafe_demo"] = True
    return plan
