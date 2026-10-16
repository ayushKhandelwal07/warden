"""Read-only summary queries for the status bar and the overview screen."""
from warden.graph.client import ro
from warden.graph.evidence import Evidence

HERO_CYPHER = """MATCH p = (:Internet)-[:REACHES]->(ing:Ingress)<-[:EXPOSED_VIA]-(entry:Service)
      -[:CALLS*0..4]->(s:Service)-[d:DEPENDS_ON]->(pkg:Package)-[a:AFFECTED_BY]->(v:Vulnerability {kev: true})
      -[:LISTED_IN]->(c:Catalog)
RETURN p, ing.name AS ingress, entry.name AS entry, s.name AS service, d.direct AS direct,
       pkg.name AS package, pkg.version AS version, pkg.ecosystem AS ecosystem, a.fixed AS fixed,
       v.id AS vuln, v.summary AS summary, v.severity AS severity, v.cvss AS cvss, v.epss AS epss,
       v.epss_percentile AS epss_percentile, v.kev_name AS kev_name, v.kev_added AS kev_added,
       v.kev_due AS kev_due, v.url AS url, length(p) - 5 AS hops
ORDER BY hops ASC, v.epss DESC
LIMIT 1"""


def health() -> dict:
    nodes, _ = ro("MATCH (n) RETURN count(n) AS n")
    edges, _ = ro("MATCH ()-[r]->() RETURN count(r) AS n")
    run, _ = ro("MATCH (r:IngestRun) RETURN r.ref AS ref, r.sha AS sha, r.at AS at ORDER BY r.at DESC LIMIT 1")
    kev, _ = ro("MATCH (c:Catalog {name: 'CISA KEV'}) RETURN c.catalog_version AS version, c.released AS released, c.entries AS entries")
    return {
        "nodes": nodes[0]["n"],
        "edges": edges[0]["n"],
        "ingest": run[0] if run else None,
        "kev": kev[0] if kev else None,
    }


def totals() -> dict:
    sev, _ = ro("MATCH (v:Vulnerability) RETURN v.severity AS severity, count(v) AS n")
    counts, _ = ro(
        """MATCH (s:Service) WITH count(s) AS services
        MATCH (p:Package) WITH services, count(p) AS packages
        MATCH (v:Vulnerability) WITH services, packages, count(v) AS vulnerabilities,
             sum(CASE WHEN v.kev THEN 1 ELSE 0 END) AS kev
        OPTIONAL MATCH (e:Service)-[:EXPOSED_VIA]->(:Ingress)
        RETURN services, packages, vulnerabilities, kev, count(DISTINCT e) AS exposed_services"""
    )
    reach, _ = ro(
        """MATCH (:Ingress)<-[:EXPOSED_VIA]-(:Service)-[:CALLS*0..4]->(s:Service)-[:DEPENDS_ON]->(:Package)-[:AFFECTED_BY]->(v:Vulnerability)
        RETURN count(DISTINCT v) AS n"""
    )
    order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
    by_sev = {r["severity"]: r["n"] for r in sev}
    return {
        **counts[0],
        "reachable_vulnerabilities": reach[0]["n"],
        "by_severity": [{"severity": s, "n": by_sev[s]} for s in order if by_sev.get(s)],
    }


def kev_hero() -> dict | None:
    """The shortest internet → KEV-listed vulnerability path, as evidence."""
    rows, ms = ro(HERO_CYPHER)
    if not rows:
        return None
    r = rows[0]
    facts = {k: v for k, v in r.items() if k != "p"}
    return {"facts": facts, "evidence": Evidence().add_path(r["p"]).to_json(), "cypher": HERO_CYPHER, "ms": ms}
