"""Policy tools: which remediation policies apply to a finding, with the reason each does or doesn't."""
import json

from warden.tools.base import Param, Result, ToolError, Trace, tool
from warden.tools.common import resolve_service, resolve_vulnerability


@tool(
    "policies_for",
    "Policies for",
    "Evaluates the org's active remediation policies against a vulnerability and/or service from graph facts "
    "(CISA KEV listing, internet reachability, severity, data sensitivity) and returns which apply and why. "
    "Agents must call this before proposing an action and cite the policy that applies.",
    [
        Param("vuln", "string", "CVE/GHSA id (optional)"),
        Param("service", "string", "Service name (optional)"),
    ],
    "policy",
    {"vuln": "CVE-2023-44487", "service": "frontend"},
)
def policies_for(trace: Trace, vuln, service, graph_name=None):
    if not vuln and not service:
        raise ToolError("Give a vulnerability, a service, or both.")
    vid = resolve_vulnerability(trace, vuln, graph_name) if vuln else None
    svc = resolve_service(trace, service, graph_name) if service else None
    facts: dict = {"vuln": vid, "service": svc}
    if vid:
        v = trace.ro("MATCH (v:Vulnerability {id: $v}) RETURN v.kev AS kev, v.severity AS severity", {"v": vid}, graph_name)[0]
        facts.update(kev=bool(v["kev"]), severity=v["severity"])
        reach = trace.ro(
            """MATCH (s:Service)-[:DEPENDS_ON]->(:Package)-[:AFFECTED_BY]->(:Vulnerability {id: $v})
WHERE $s IS NULL OR s.name = $s
OPTIONAL MATCH p = (:Ingress)<-[:EXPOSED_VIA]-(:Service)-[:CALLS*0..4]->(s)
RETURN count(p) > 0 AS reachable""",
            {"v": vid, "s": svc},
            graph_name,
        )
        facts["reachable"] = bool(reach and reach[0]["reachable"])
    if svc:
        d = trace.ro("MATCH (:Service {name: $s})-[:READS]->(d:DataAsset) RETURN collect(DISTINCT d.sensitivity) AS s", {"s": svc}, graph_name)
        facts["data_sensitivity"] = d[0]["s"] if d else []
    pols = trace.ro(
        "MATCH (p:Policy) WHERE p.active = true RETURN p.id AS id, p.rule_text AS rule, p.conditions_json AS cond, "
        "p.due_hours AS due_hours, p.source AS source, p.priority AS priority ORDER BY p.priority, p.id",
        graph_name=graph_name,
    )
    out = []
    for p in pols:
        cond = json.loads(p["cond"] or "{}")
        reasons, applies, known = [], True, True
        for k, want in cond.items():
            have = facts.get(k)
            if have is None:
                known = False
                reasons.append(f"{k} unknown")
                continue
            if k == "severity":
                ok = have in want
            elif k == "data_sensitivity":
                ok = want in have
            else:
                ok = have == want
            applies &= ok
            reasons.append(f"{k}={have if not isinstance(have, list) else '/'.join(have) or 'none'} {'✓' if ok else '✗'}")
        out.append(
            {"policy": p["id"], "applies": applies and known, "why": ", ".join(reasons), "rule": p["rule"],
             "due_hours": p["due_hours"], "source": p["source"]}
        )
    hits = [o for o in out if o["applies"]]
    target = " / ".join(x for x in [vid, svc] if x)
    summary = (
        f"{len(hits)} polic{'y applies' if len(hits) == 1 else 'ies apply'} to {target}: "
        + "; ".join(f"{h['policy']} ({h['rule']})" for h in hits)
        if hits
        else f"No active policy applies to {target}."
    )
    return Result(summary, out, ["policy", "applies", "why", "due_hours", "rule"], None, sources=["org/policies.yaml (curated)"])
