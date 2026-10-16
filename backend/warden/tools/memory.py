"""Decision memory: what the org already decided about a vulnerability or service, across sessions."""
from datetime import datetime, timezone

from warden.graph.evidence import Evidence
from warden.tools.base import Param, Result, ToolError, Trace, tool
from warden.tools.common import resolve_service, resolve_vulnerability


def _date(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ms else None


@tool(
    "decisions_about",
    "Decisions about",
    "Past decisions recorded in the graph (approved, rejected with the reason, verified fixed) about a vulnerability "
    "or a service, newest first, with links to what they produced. Use for 'what did we decide about X' and before "
    "proposing an action someone already rejected.",
    [
        Param("vuln", "string", "CVE/GHSA id (optional)"),
        Param("service", "string", "Service name (optional)"),
    ],
    "memory",
    {"vuln": "CVE-2023-44487"},
)
def decisions_about(trace: Trace, vuln, service, graph_name=None):
    if not vuln and not service:
        raise ToolError("Give a vulnerability, a service, or both.")
    vid = resolve_vulnerability(trace, vuln, graph_name) if vuln else None
    svc = resolve_service(trace, service, graph_name) if service else None
    rows = trace.ro(
        """MATCH (d:Decision)
WHERE ($v IS NULL OR (d)-[:ABOUT]->(:Vulnerability {id: $v})) AND ($s IS NULL OR (d)-[:CHANGES]->(:Service {name: $s}))
OPTIONAL MATCH (d)-[:CHANGES]->(x:Service)
RETURN d.id AS id, d.kind AS kind, d.text AS text, d.status AS status, d.reason AS reason, d.decided_at AS decided_at,
       d.links AS links, collect(DISTINCT x.name) AS services
ORDER BY decided_at DESC LIMIT 10""",
        {"v": vid, "s": svc},
        graph_name,
    )
    target = " / ".join(x for x in [vid, svc] if x)
    if not rows:
        return Result(f"No decision about {target} is recorded in the graph.", [], None, None)
    ev = Evidence()
    paths = trace.ro(
        """MATCH p = (d:Decision)-[:ABOUT]->(v:Vulnerability {id: $v}) RETURN p ORDER BY d.decided_at DESC LIMIT 3""" if vid else
        """MATCH p = (d:Decision)-[:CHANGES]->(s:Service {name: $s}) RETURN p ORDER BY d.decided_at DESC LIMIT 3""",
        {"v": vid} if vid else {"s": svc},
        graph_name,
    )
    for p in paths:
        ev.add_path(p["p"])
    out = [
        {"decided": _date(r["decided_at"]), "status": r["status"], "decision": r["text"], "reason": r["reason"],
         "services": ", ".join(r["services"]), "links": ", ".join(r["links"] or [])}
        for r in rows
    ]
    last = out[0]
    summary = f"{len(out)} decision(s) about {target}. Latest ({last['decided']}): {last['status']}: {last['decision']}" + (
        f", reason: {last['reason']}" if last["reason"] else ""
    ) + "."
    return Result(summary, out, ["decided", "status", "decision", "reason", "services"], ev)
