"""Counterfactuals: apply hypothetical changes to a copy of the graph, recompute, and report what moves.

Changes (a list of dicts):
  {"op": "expose",      "service": s}                  s gets a public LoadBalancer
  {"op": "unexpose",    "service": s}                  s loses its public ingress
  {"op": "remove_dep",  "service": s, "package": name}  s stops depending on a package
  {"op": "remove_call", "from": a, "to": b}             a stops calling b
  {"op": "upgrade",     "package": name}                the package moves to a version that fixes every advisory that lists a fix
                                                       (assumption: new advisories on the target version are not modelled; use a plan for that)

The live graph is never written. The copy is always deleted.
"""
import uuid

from warden import config, regression
from warden.graph.client import copy_graph, delete_graph, ro, rw
from warden.sync import diff_graphs
from warden.tools.base import Trace
from warden.tools.security import best_findings, scored_paths
from warden.tools.topology import SENSITIVE_ROUTES_CYPHER

OPS = {"expose", "unexpose", "remove_dep", "remove_call", "upgrade"}


def describe(c: dict) -> str:
    op = c["op"]
    return {
        "expose": f"expose {c.get('service')} to the internet",
        "unexpose": f"remove {c.get('service')} from the public ingress",
        "remove_dep": f"remove {c.get('package')} from {c.get('service')}",
        "remove_call": f"stop {c.get('from')} calling {c.get('to')}",
        "upgrade": f"upgrade {c.get('package')} to a fixed version",
    }[op]


def _check(g: str, c: dict) -> None:
    if c.get("op") not in OPS:
        raise ValueError(f"Unknown change '{c.get('op')}'. Use one of {', '.join(sorted(OPS))}.")
    names = [c[k] for k in ("service", "from", "to") if c.get(k)]
    for n in names:
        if not ro("MATCH (s:Service {name: $n}) RETURN s.name AS n", {"n": n}, g)[0]:
            raise ValueError(f"Service '{n}' is not in the graph")
    if c["op"] in ("remove_dep", "upgrade") and not c.get("package"):
        raise ValueError(f"'{c['op']}' needs a package name")
    if c["op"] in ("expose", "unexpose", "remove_dep") and not c.get("service"):
        raise ValueError(f"'{c['op']}' needs a service")
    if c["op"] == "remove_call" and not (c.get("from") and c.get("to")):
        raise ValueError("'remove_call' needs from and to")


def apply(g: str, c: dict) -> None:
    _check(g, c)
    op = c["op"]
    if op == "expose":
        rw("""MATCH (s:Service {name: $s}), (net:Internet) MERGE (i:Ingress {name: $ing}) SET i.kind = 'LoadBalancer', i.what_if = true
              MERGE (s)-[:EXPOSED_VIA]->(i) MERGE (net)-[:REACHES]->(i)""", {"s": c["service"], "ing": f"{c['service']}-external"}, g)
    elif op == "unexpose":
        rw("MATCH (s:Service {name: $s})-[e:EXPOSED_VIA]->(:Ingress) DELETE e", {"s": c["service"]}, g)
    elif op == "remove_dep":
        rw("MATCH (s:Service {name: $s})-[d:DEPENDS_ON]->(p:Package) WHERE p.name = $p DELETE d", {"s": c["service"], "p": c["package"]}, g)
    elif op == "remove_call":
        rw("MATCH (a:Service {name: $a})-[x:CALLS]->(b:Service {name: $b}) DELETE x", {"a": c["from"], "b": c["to"]}, g)
    else:
        rw("MATCH (p:Package {name: $p})-[a:AFFECTED_BY]->(:Vulnerability) WHERE a.fixed IS NOT NULL DELETE a", {"p": c["package"]}, g)


def _routes(g: str) -> set[tuple]:
    rows, _ = ro(SENSITIVE_ROUTES_CYPHER, {"weight": regression.SENSITIVE_WEIGHT}, g)
    return {(" → ".join(r["route"]), r["asset"]) for r in rows}


def _state(g: str, assets: dict) -> dict:
    f = best_findings(scored_paths(Trace(), graph_name=g))
    return {"findings": f, "risk": round(sum(x["risk"] for x in f), 1), "kev": sum(1 for x in f if x["kev"]),
            "routes": _routes(g), "data": regression.invariants(f, assets)["data"]}


def _ranks(findings: list[dict], n: int = 10) -> dict:
    return {(f["vuln"], f["service"]): i + 1 for i, f in enumerate(findings[:n])}


def _measure(live: str, copy: str, assets: dict, before: dict) -> dict:
    after = _state(copy, assets)
    rb, ra = _ranks(before["findings"]), _ranks(after["findings"])
    all_after = {(f["vuln"], f["service"]): i + 1 for i, f in enumerate(after["findings"])}
    all_before = {(f["vuln"], f["service"]): i + 1 for i, f in enumerate(before["findings"])}
    moved = [{"vuln": k[0], "service": k[1], "before": all_before.get(k), "after": all_after.get(k)}
             for k in sorted(set(rb) | set(ra)) if all_before.get(k) != all_after.get(k)]
    moved.sort(key=lambda m: (m["after"] is None, m["after"] or 0, m["before"] or 0))
    return {
        "after": after,
        "routes_new": sorted(after["routes"] - before["routes"]),
        "routes_removed": sorted(before["routes"] - after["routes"]),
        "assets_new": sorted({a for _, a in after["routes"]} - {a for _, a in before["routes"]}),
        "assets_removed": sorted({a for _, a in before["routes"]} - {a for _, a in after["routes"]}),
        "rank_changes": moved[:10],
    }


def _candidates(live: str, diff: dict) -> list[dict]:
    """Counter-moves worth trying: take the newly risky services and either close their ingress or cut the calls into them."""
    risky = []
    for r in sorted(diff["new"] + diff["worse"], key=lambda r: -r["risk"]):
        if r["service"] not in risky:
            risky.append(r["service"])
    out = []
    for s in risky[:3]:
        if ro("MATCH (:Service {name: $s})-[:EXPOSED_VIA]->(:Ingress) RETURN 1 AS x LIMIT 1", {"s": s}, live)[0]:
            out.append({"op": "unexpose", "service": s})
        for r in ro("MATCH (a:Service)-[:CALLS]->(:Service {name: $s}) RETURN a.name AS a LIMIT 2", {"s": s}, live)[0]:
            out.append({"op": "remove_call", "from": r["a"], "to": s})
    return out[:6]


def what_if(changes: list[dict], find_best: bool = False) -> dict:
    live = config.org_graph_name()
    changes = [dict(c) for c in changes if c]
    if not changes:
        raise ValueError("Give at least one change.")
    if len(changes) > 6:
        raise ValueError("At most 6 changes at a time.")
    copy = f"{live}_whatif_{uuid.uuid4().hex[:8]}"
    copy_graph(live, copy)
    try:
        trace = Trace()
        assets = regression.sensitive_assets(trace, live)
        before = _state(live, assets)
        for c in changes:
            apply(copy, c)
        diff = diff_graphs(live, copy)
        m = _measure(live, copy, assets, before)
        best = None
        if find_best:
            tried = []
            for cand in _candidates(copy, diff):
                alt = f"{live}_whatif_{uuid.uuid4().hex[:8]}"
                copy_graph(copy, alt)
                try:
                    apply(alt, cand)
                    s = _state(alt, assets)
                    tried.append({"change": cand, "label": describe(cand), "risk_after": s["risk"], "risk_recovered": round(m["after"]["risk"] - s["risk"], 1),
                                  "routes_removed": len(m["after"]["routes"] - s["routes"]), "kev_after": s["kev"]})
                finally:
                    delete_graph(alt)
            tried.sort(key=lambda t: (-t["risk_recovered"], -t["routes_removed"], t["label"]))
            best = {"tried": tried, "best": tried[0] if tried and tried[0]["risk_recovered"] > 0 else None}
    finally:
        delete_graph(copy)
    a = m["after"]
    return {
        "changes": [{**c, "label": describe(c)} for c in changes],
        "graph": copy, "deleted": True, **diff,
        "paths": {"before": len(before["routes"]), "after": len(a["routes"]), "new": m["routes_new"], "removed": m["routes_removed"]},
        "sensitive": {"new_assets": m["assets_new"], "no_longer_reachable": m["assets_removed"]},
        "risk": {"before": before["risk"], "after": a["risk"], "kev_before": before["kev"], "kev_after": a["kev"]},
        "rank_changes": m["rank_changes"],
        "intervention": best,
        "assumption": "Structural model: CALLS edges inferred from manifests, no runtime traffic data. 'Upgrade' assumes the fixed version carries no new advisory.",
    }


def what_if_expose(service: str) -> dict:
    """Compatibility wrapper for the original single-service rehearsal."""
    return {"service": service, **what_if([{"op": "expose", "service": service}])}
