"""Security tools: which vulnerabilities can the internet reach, how exploited are they, and what to change."""
from warden.graph.evidence import Evidence
from warden.tools.base import Param, Result, ToolError, Trace, tool
from warden.tools.common import resolve_service, resolve_vulnerability
from warden.tools.risk import TIER_ASSUMPTION, risk_factors, tier_of

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]

FINDINGS_CYPHER = """
MATCH (:Ingress)<-[:EXPOSED_VIA]-(entry:Service)
MATCH p = (entry)-[:CALLS*0..4]->(s:Service)
WITH s, min(length(p)) AS hops
MATCH (s)-[d:DEPENDS_ON]->(pkg:Package)-[a:AFFECTED_BY]->(v:Vulnerability)
WHERE v.severity IN $severities AND ($service IS NULL OR s.name = $service)
OPTIONAL MATCH (s)-[:READS]->(da:DataAsset)
WITH s, hops, d, pkg, a, v, max(da.weight) AS data_weight, collect(DISTINCT da.name) AS data
RETURN v.id AS vuln, v.severity AS severity, v.cvss AS cvss, v.kev AS kev, v.epss AS epss, v.summary AS summary,
       s.name AS service, hops, pkg.key AS package_key, pkg.name AS package, pkg.version AS version,
       pkg.ecosystem AS ecosystem, d.direct AS direct, d.manifest AS manifest, a.fixed AS fixed, data_weight, data"""

FINDING_PATH_CYPHER = """
MATCH p = (:Internet)-[:REACHES]->(:Ingress)<-[:EXPOSED_VIA]-(:Service)-[:CALLS*0..4]->(s:Service {name: $service})
      -[:DEPENDS_ON]->(:Package {key: $package_key})-[:AFFECTED_BY]->(v:Vulnerability {id: $vuln})
RETURN p ORDER BY length(p) ASC LIMIT 1"""


def _attach_context(trace: Trace, ev: Evidence, vuln: str, service: str, order_after: int, graph_name):
    """Adds the KEV catalog hop and the sensitive data the service reads, so the path shows *why* it matters."""
    rows = trace.ro(
        """MATCH (v:Vulnerability {id: $vuln}) OPTIONAL MATCH (v)-[l:LISTED_IN]->(c:Catalog)
        OPTIONAL MATCH (s:Service {name: $service})-[r:READS]->(d:DataAsset)
        RETURN c, l, collect(DISTINCT [r, d]) AS reads""",
        {"vuln": vuln, "service": service},
        graph_name,
    )
    if not rows:
        return
    r = rows[0]
    if r["c"] is not None:
        ev.add_node(r["c"], order_after + 1)
        ev.add_edge(r["l"])
    for pair in r["reads"]:
        if pair and pair[0] is not None:
            ev.add_node(pair[1], order_after)
            ev.add_edge(pair[0])


def scored_paths(trace: Trace, severities=SEVERITIES, service=None, graph_name=None) -> list[dict]:
    """Every internet-reachable (vulnerability, service, package) path with its explained risk. Shared with the planner."""
    out = []
    for r in trace.ro(FINDINGS_CYPHER, {"severities": severities, "service": service}, graph_name):
        f = risk_factors(r["severity"], r["cvss"], r["kev"], r["epss"], r["hops"], r["data_weight"])
        out.append(
            {
                "risk": f["risk"], "vuln": r["vuln"], "kev": bool(r["kev"]), "epss": r["epss"], "severity": r["severity"],
                "cvss": r["cvss"], "service": r["service"], "hops": r["hops"],
                "package": f"{r['package']}@{str(r['version']).lstrip('v')}", "package_key": r["package_key"],
                "package_name": r["package"], "version": r["version"], "ecosystem": r["ecosystem"], "direct": r["direct"],
                "manifest": r["manifest"], "fixed": r["fixed"], "data": r["data"], "data_weight": r["data_weight"], "driver": f["driver"],
                "factors": f["factors"], "summary": r["summary"],
                "tier": tier_of(bool(r["kev"]), r["epss"]),
                # The entry service's own dependencies are sourced from lockfiles; deeper hops rely on inferred CALLS edges.
                "confidence": "sourced" if r["hops"] == 0 else "inferred",
            }
        )
    return out


def best_findings(paths: list[dict]) -> list[dict]:
    """One finding per (vulnerability, service): the riskiest package path that carries it."""
    best: dict[tuple, dict] = {}
    for item in paths:
        k = (item["vuln"], item["service"])
        if k not in best or item["risk"] > best[k]["risk"]:
            best[k] = item
    return sorted(best.values(), key=lambda x: (-x["risk"], x["vuln"], x["service"]))


@tool(
    "reachable_findings",
    "Reachable findings",
    "Vulnerabilities an internet attacker can reach, ranked by risk = severity × exploit (CISA KEV / EPSS) × exposure "
    "(halves per hop behind the internet-facing service) × sensitivity of the data the service reads. Each finding comes "
    "with its attack path. Use for 'what should we fix first' and 'is X reachable'.",
    [
        Param("severities", "string[]", "Severities to include", default=SEVERITIES, choices=SEVERITIES),
        Param("service", "string", "Only findings in this service (optional)"),
        Param("limit", "integer", "How many findings to return", default=10, minimum=1, maximum=50),
        Param("paths", "integer", "How many top findings get their full attack path drawn", default=3, minimum=0, maximum=8),
    ],
    "security",
    {"limit": 10},
)
def reachable_findings(trace: Trace, severities, service, limit, paths, graph_name=None):
    if service:
        service = resolve_service(trace, service, graph_name)
    findings = best_findings(scored_paths(trace, severities, service, graph_name))
    total = trace.ro("MATCH (v:Vulnerability) RETURN count(v) AS n", graph_name=graph_name)[0]["n"]
    reachable_vulns = {f["vuln"] for f in findings}

    ev = Evidence()
    for f in findings[:paths]:
        prow = trace.ro(FINDING_PATH_CYPHER, {"service": f["service"], "package_key": f["package_key"], "vuln": f["vuln"]}, graph_name)
        if prow:
            p = prow[0]["p"]
            ev.add_path(p)
            _attach_context(trace, ev, f["vuln"], f["service"], len(p.nodes()) - 1, graph_name)

    scope = f" in {service}" if service else ""
    if not findings:
        known = trace.ro(
            """MATCH (s:Service)-[:DEPENDS_ON]->(:Package)-[:AFFECTED_BY]->(v:Vulnerability)
WHERE ($service IS NULL OR s.name = $service) AND v.severity IN $severities RETURN count(DISTINCT v) AS n""",
            {"service": service, "severities": severities},
            graph_name,
        )[0]["n"]
        summary = (
            f"No path in the graph: none of the {known} known {'/'.join(severities)} vulnerabilities{scope} "
            "are graph-reachable from the internet-facing service."
        )
    else:
        top = findings[0]
        intel = "on CISA KEV (known exploitation reported)" if top["kev"] else f"EPSS {(top['epss'] or 0):.1%} (a likelihood estimate)"
        signal = len({f["vuln"] for f in findings if f["tier"] == "exploit_signal"})
        summary = (
            f"{len(reachable_vulns)} of {total} known advisories{scope} are graph-reachable from the internet-facing service "
            f"under the current topology model; {signal} of them carry an exploit signal (CISA KEV or EPSS of 10% or more). "
            f"Highest risk: {top['vuln']} in {top['package']} on {top['service']} "
            f"({intel}, {top['hops']} hop(s) from the internet), tier {top['tier']}, risk {top['risk']}, driven by {top['driver']}. "
            f"Assumption: {TIER_ASSUMPTION}"
        )
    cols = ["risk", "tier", "vuln", "kev", "severity", "service", "hops", "package", "fixed", "driver"]
    return Result(summary, findings[:limit], cols, ev, sources=[f"https://osv.dev/vulnerability/{f['vuln']}" for f in findings[:3]])


@tool(
    "exploit_intel",
    "Exploit intel",
    "Threat intelligence for one vulnerability: CISA KEV listing (exploited in the wild), EPSS exploit probability, "
    "CVSS, and every service and package it affects with how far each is from the internet.",
    [Param("vuln", "string", "CVE, GHSA or OSV id", required=True)],
    "security",
    {"vuln": "CVE-2023-44487"},
)
def exploit_intel(trace: Trace, vuln, graph_name=None):
    vid = resolve_vulnerability(trace, vuln, graph_name)
    v = trace.ro(
        """MATCH (v:Vulnerability {id: $v}) OPTIONAL MATCH (v)-[l:LISTED_IN]->(c:Catalog)
        RETURN v, l, c""",
        {"v": vid},
        graph_name,
    )[0]
    vp = v["v"].properties
    affected = trace.ro(
        """MATCH (s:Service)-[d:DEPENDS_ON]->(pkg:Package)-[a:AFFECTED_BY]->(v:Vulnerability {id: $v})
        OPTIONAL MATCH p = (:Ingress)<-[:EXPOSED_VIA]-(:Service)-[:CALLS*0..4]->(s)
        WITH s, d, pkg, a, min(length(p)) - 1 AS hops
        RETURN s.name AS service, pkg.name + '@' + pkg.version AS package, d.direct AS direct, a.fixed AS fixed,
               hops AS hops_from_internet
        ORDER BY hops_from_internet, service""",
        {"v": vid},
        graph_name,
    )
    ev = Evidence()
    paths = trace.ro(
        """MATCH p = (s:Service)-[:DEPENDS_ON]->(:Package)-[:AFFECTED_BY]->(v:Vulnerability {id: $v}) RETURN p LIMIT 8""",
        {"v": vid},
        graph_name,
    )
    for r in paths:
        ev.add_path(r["p"])
    if v["c"] is not None:
        ev.add_node(v["c"], 3)
        ev.add_edge(v["l"])
    kev = (
        f"On CISA KEV since {vp.get('kev_added')} ({vp.get('kev_name')}); federal due date {vp.get('kev_due')}"
        + ("; used in ransomware campaigns" if vp.get("kev_ransomware") else "")
        if vp.get("kev")
        else "Not on the CISA KEV list"
    )
    epss = vp.get("epss")
    summary = (
        f"{vid} ({vp.get('severity')}, CVSS {vp.get('cvss')}). {kev}. "
        f"EPSS {int(epss * 10000) / 100:.2f}% chance of exploitation in the next 30 days. " if epss is not None else f"{vid}. {kev}. No EPSS score. "
    ) + f"Affects {len(affected)} service/package pair(s)."
    for a in affected:
        a["hops_from_internet"] = a["hops_from_internet"] if a["hops_from_internet"] is not None and a["hops_from_internet"] >= 0 else None
    return Result(summary, affected, None, ev, sources=[vp.get("url")] + (["https://www.cisa.gov/known-exploited-vulnerabilities-catalog"] if vp.get("kev") else []))


@tool(
    "fix_path",
    "Fix path",
    "What exactly to change to remove a vulnerability from a service: which manifest file, which line, from which "
    "version to which. For transitive npm packages it walks the REQUIRES chain from the direct dependency and proposes "
    "an `overrides` entry; for the Go standard library it proposes the builder image bump.",
    [
        Param("vuln", "string", "CVE, GHSA or OSV id", required=True),
        Param("service", "string", "Service to fix", required=True),
    ],
    "security",
    {"vuln": "CVE-2026-4800", "service": "paymentservice"},
)
def fix_path(trace: Trace, vuln, service, graph_name=None):
    vid = resolve_vulnerability(trace, vuln, graph_name)
    svc = resolve_service(trace, service, graph_name)
    rows = trace.ro(
        """MATCH (s:Service {name: $s})-[d:DEPENDS_ON]->(pkg:Package)-[a:AFFECTED_BY]->(v:Vulnerability {id: $v})
        RETURN pkg.key AS key, pkg.name AS name, pkg.version AS version, pkg.ecosystem AS ecosystem,
               d.direct AS direct, d.manifest AS manifest, d.source_url AS url, a.fixed AS fixed""",
        {"s": svc, "v": vid},
        graph_name,
    )
    if not rows:
        raise ToolError(f"{vid} does not affect {svc}: no DEPENDS_ON → AFFECTED_BY path between them in the graph.")
    ev = Evidence()
    changes = []
    for r in rows:
        chain = []
        if not r["direct"] and r["ecosystem"] in ("npm", "PyPI"):
            cp = trace.ro(
                """MATCH p = (s:Service {name: $s})-[:DEPENDS_ON {direct: true}]->(:Package)-[:REQUIRES*1..8]->(pkg:Package {key: $k})
                RETURN p ORDER BY length(p) ASC LIMIT 1""",
                {"s": svc, "k": r["key"]},
                graph_name,
            )
            if cp:
                p = cp[0]["p"]
                ev.add_path(p)
                chain = [n.properties.get("name") for n in p.nodes()[1:]]
        if not chain:
            dp = trace.ro(
                "MATCH p = (s:Service {name: $s})-[:DEPENDS_ON]->(:Package {key: $k}) RETURN p", {"s": svc, "k": r["key"]}, graph_name
            )
            if dp:
                ev.add_path(dp[0]["p"])
        to = r["fixed"] or "no fixed version published"
        frm = str(r["version"])
        if r["name"] == "stdlib":
            change = f"Bump the Go builder image to golang:{to}"
            file = r["manifest"]
        elif r["ecosystem"] == "Go":
            change = f"go.mod: {r['name']} {frm} → v{to.lstrip('v')}" + ("" if r["direct"] else " (indirect line)") + ", then `go mod tidy`"
            file = r["manifest"]
        elif r["ecosystem"] == "npm" and not r["direct"]:
            change = f'package.json "overrides": {{"{r["name"]}": "{to}"}} (pulled in via {" → ".join(chain) or "a transitive dependency"}), then `npm install`'
            file = r["manifest"].replace("package-lock.json", "package.json")
        elif r["ecosystem"] == "npm":
            change = f'package.json dependency "{r["name"]}": "{to}", then `npm install`'
            file = r["manifest"].replace("package-lock.json", "package.json")
        elif r["ecosystem"] == "PyPI":
            change = f"requirements.txt: {r['name']}=={frm} → =={to}" + (f" (needed by {' → '.join(chain)})" if chain else "")
            file = r["manifest"]
        else:
            change = f"{r['name']}: {frm} → {to}"
            file = r["manifest"]
        changes.append(
            {"package": f"{r['name']}@{frm.lstrip('v')}", "ecosystem": r["ecosystem"], "direct": r["direct"], "file": file,
             "from": frm, "to": to, "change": change, "via": " → ".join(chain) if chain else None}
        )
    vnode = trace.ro("MATCH (v:Vulnerability {id: $v}) RETURN v", {"v": vid}, graph_name)[0]["v"]
    max_order = max((n.get("order") or 0) for n in ev.nodes.values()) if ev else 0
    ev.add_node(vnode, max_order + 1)
    aff = trace.ro(
        "MATCH (:Service {name: $s})-[:DEPENDS_ON]->(pkg:Package)-[a:AFFECTED_BY]->(:Vulnerability {id: $v}) RETURN a",
        {"s": svc, "v": vid},
        graph_name,
    )
    for r in aff:
        ev.add_edge(r["a"])
    first = changes[0]
    summary = f"To remove {vid} from {svc}: {first['change']} in {first['file']}." + (
        f" ({len(changes) - 1} more package edge(s) below.)" if len(changes) > 1 else ""
    )
    return Result(summary, changes, ["package", "direct", "file", "from", "to", "change"], ev)
