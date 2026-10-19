"""Names to use in examples and suggested questions, read from the current project's graph, so every project's UI
asks about its own services, data and advisories (never a name that only exists in the demo graph)."""
from warden.graph.client import ro


def _one(cypher: str, key: str, params: dict | None = None):
    rows, _ = ro(cypher, params or {})
    return rows[0][key] if rows else None


def names() -> dict:
    services = [r["n"] for r in ro("MATCH (s:Service) OPTIONAL MATCH (s)-[:EXPOSED_VIA]->(i:Ingress) RETURN s.name AS n, count(i) > 0 AS pub ORDER BY pub DESC, n")[0]]
    public = _one("MATCH (s:Service)-[:EXPOSED_VIA]->(:Ingress) RETURN s.name AS n ORDER BY n LIMIT 1", "n")
    asset = _one("MATCH (:Service)-[:READS]->(d:DataAsset) RETURN d.name AS n, max(d.weight) AS w ORDER BY w DESC, n LIMIT 1", "n")
    # The service to protect: reads the most sensitive data, isn't itself internet-facing, and calls the fewest others.
    service = _one(
        """MATCH (s:Service)-[:READS]->(d:DataAsset) WHERE NOT (s)-[:EXPOSED_VIA]->(:Ingress)
        OPTIONAL MATCH (s)-[c:CALLS]->() RETURN s.name AS n, max(d.weight) AS w, count(c) AS calls ORDER BY w DESC, calls, n LIMIT 1""", "n",
    ) or _one(
        """MATCH (s:Service)-[:DEPENDS_ON]->(:Package)-[:AFFECTED_BY]->(v:Vulnerability)
        RETURN s.name AS n, count(DISTINCT v) AS k ORDER BY k DESC, n LIMIT 1""", "n",
    ) or (services[0] if services else None)
    caller = _one("MATCH (a:Service)-[:CALLS]->(:Service {name: $s}) RETURN a.name AS n ORDER BY n LIMIT 1", "n", {"s": service})
    top = ro(
        """MATCH (s:Service)-[:DEPENDS_ON]->(p:Package)-[:AFFECTED_BY]->(v:Vulnerability)
        RETURN v.id AS vuln, p.name AS package, s.name AS service
        ORDER BY v.kev DESC, coalesce(v.epss, 0) DESC, coalesce(v.cvss, 0) DESC, v.id LIMIT 1"""
    )[0]
    # A service the watcher's demo change can expose: internal, declared in a Kubernetes manifest the change can edit.
    exposable = [r["n"] for r in ro(
        """MATCH (s:Service) WHERE NOT (s)-[:EXPOSED_VIA]->(:Ingress) AND (s.source_url ENDS WITH '.yaml' OR s.source_url ENDS WITH '.yml')
        RETURN s.name AS n ORDER BY n"""
    )[0]]
    person = _one("MATCH (p:Person)-[k:KNOWS]->(:Service) WHERE p.login IS NOT NULL RETURN p.login AS n, sum(k.commits) AS c ORDER BY c DESC LIMIT 1", "n")
    pr = _one("MATCH (pr:PullRequest)-[:CONTAINS]->(:Commit)-[:TOUCHES]->(:File)-[:BELONGS_TO]->(:Service) RETURN pr.number AS n ORDER BY pr.merged_at DESC LIMIT 1", "n")
    return {
        "services": services, "service": service, "caller": caller, "public": public, "asset": asset,
        "vuln": top[0]["vuln"] if top else None, "package": top[0]["package"] if top else None,
        "vuln_service": top[0]["service"] if top else None, "person": person, "pr": pr,
        "exposable": service if service in exposable else (exposable[0] if exposable else None),
    }


def _exists(label: str, key: str, value) -> bool:
    return bool(ro(f"MATCH (x:{label} {{{key}: $v}}) RETURN x LIMIT 1", {"v": value})[0])


def localize(example: dict, n: dict) -> dict:
    """A tool's example arguments, with every name that doesn't exist in this graph swapped for one that does."""
    svcs = set(n["services"])
    out = dict(example)
    if "vuln" in out and not _exists("Vulnerability", "id", out["vuln"]) and n["vuln"]:
        out["vuln"] = n["vuln"]
        if "service" in out and n["vuln_service"]:
            out["service"] = n["vuln_service"]
    if "service" in out and out["service"] not in svcs:
        # With an advisory, the service has to be one that ships it; otherwise the service worth protecting.
        hit = ro("MATCH (s:Service)-[:DEPENDS_ON]->(:Package)-[:AFFECTED_BY]->(:Vulnerability {id: $v}) RETURN s.name AS n ORDER BY n LIMIT 1",
                 {"v": out["vuln"]})[0] if "vuln" in out else []
        out["service"] = (hit[0]["n"] if hit else n["service"]) or out["service"]
    if "services" in out:
        keep = [s for s in out["services"] if s in svcs]
        out["services"] = keep or list(dict.fromkeys(s for s in (n["public"], n["service"], *n["services"][:2]) if s))[:2] or out["services"]
    if "package" in out and n["package"] and not _exists("Package", "name", out["package"]):
        out["package"] = n["package"]
    if "source" in out and out["source"] not in svcs and n["public"]:
        out["source"] = n["public"]
    if "target" in out and out["target"] not in svcs and not _exists("DataAsset", "name", out["target"]):
        others = [s for s in n["services"] if s != out.get("source")]
        out["target"] = n["asset"] or (n["service"] if n["service"] != out.get("source") else None) or (others[0] if others else out["target"])
    if "pr" in out and n["pr"] and not _exists("PullRequest", "number", out["pr"]):
        out["pr"] = n["pr"]
    if "text" in out and n["service"] and not any(out["text"] in s for s in svcs):
        out["text"] = n["service"][:8]
    return out
