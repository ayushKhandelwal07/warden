"""The whole attack surface as one small graph: Internet, the services by hop distance, and the sensitive data they read.

Everything is read from the live graph. Per-service risk is the sum of the scored exposures in that service, so a service that
ships many reachable advisories looks heavier than one with a single low-risk advisory. The thick path is the shortest call route
from the internet-facing service to each service that carries a CISA KEV exposure.
"""
from collections import deque

from warden import regression
from warden.tools.base import Trace
from warden.tools.security import best_findings, scored_paths
from warden.tools.topology import SENSITIVE_ROUTES_CYPHER


def kev_edges(entry: list[str], calls: list[tuple[str, str]], kev_services: set[str]) -> list[tuple[str, str]]:
    """Pure: edges on the shortest call route from any entry service to each KEV service (breadth-first)."""
    adj: dict[str, list[str]] = {}
    for a, b in calls:
        adj.setdefault(a, []).append(b)
    parent: dict[str, str | None] = {e: None for e in entry}
    q = deque(entry)
    while q:
        cur = q.popleft()
        for nxt in adj.get(cur, []):
            if nxt not in parent:
                parent[nxt] = cur
                q.append(nxt)
    out: set[tuple[str, str]] = set()
    for s in kev_services:
        while s in parent and parent[s] is not None:
            out.add((parent[s], s))
            s = parent[s]
    return sorted(out)


def build(graph_name: str | None = None) -> dict:
    t = Trace()
    findings = best_findings(scored_paths(t, graph_name=graph_name))
    risk: dict[str, float] = {}
    count: dict[str, int] = {}
    kev_svc: set[str] = set()
    for f in findings:
        risk[f["service"]] = risk.get(f["service"], 0) + f["risk"]
        count[f["service"]] = count.get(f["service"], 0) + 1
        if f["kev"]:
            kev_svc.add(f["service"])
    entry = [r["s"] for r in t.ro("MATCH (s:Service)-[:EXPOSED_VIA]->(:Ingress) RETURN DISTINCT s.name AS s", graph_name=graph_name)]
    hops = {r["s"]: r["h"] for r in t.ro(
        """MATCH (:Ingress)<-[:EXPOSED_VIA]-(e:Service) MATCH p = (e)-[:CALLS*0..4]->(s:Service) RETURN s.name AS s, min(length(p)) AS h""", graph_name=graph_name)}
    names = [r["s"] for r in t.ro("MATCH (s:Service) RETURN s.name AS s ORDER BY s", graph_name=graph_name)]
    calls = [(r["a"], r["b"]) for r in t.ro("MATCH (a:Service)-[:CALLS]->(b:Service) RETURN a.name AS a, b.name AS b", graph_name=graph_name)]
    assets = regression.sensitive_assets(t, graph_name)
    reads = t.ro("MATCH (s:Service)-[:READS]->(d:DataAsset) WHERE d.weight >= $w RETURN s.name AS s, d.name AS d", {"w": regression.SENSITIVE_WEIGHT}, graph_name)
    routes = t.ro(SENSITIVE_ROUTES_CYPHER, {"weight": regression.SENSITIVE_WEIGHT}, graph_name)
    reach_calls = [(a, b) for a, b in calls if a in hops and b in hops]
    return {
        "services": [{"name": n, "hops": hops.get(n), "risk": round(risk.get(n, 0), 1), "exposures": count.get(n, 0), "kev": n in kev_svc, "entry": n in entry,
                      "reads": sorted(r["d"] for r in reads if r["s"] == n)} for n in names],
        "assets": [{"name": a["name"], "sensitivity": a["sensitivity"], "weight": a["weight"]} for a in assets.values()],
        "calls": [{"from": a, "to": b} for a, b in calls],
        "kev_path": [{"from": a, "to": b} for a, b in kev_edges(entry, reach_calls, kev_svc)],
        "routes": [{"route": r["route"], "asset": r["asset"]} for r in routes],
        "entry": entry,
        "max_risk": max(risk.values(), default=0),
    }
