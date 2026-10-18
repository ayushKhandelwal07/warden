"""Decision memory: what the org already decided about a vulnerability or service, across sessions."""
import json
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
       d.links AS links, d.items_json AS items, d.ingest_sha AS sha, d.decided_by AS by, collect(DISTINCT x.name) AS services
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
    from warden import memory

    versions, sha = memory.current_versions(), memory.ingest_sha()

    def applies(r):
        d = {"status": r["status"], "at": r["decided_at"], "sha": r["sha"], "items": json.loads(r["items"] or "[]")}
        return memory.applies_now(d, versions, sha)

    out = [
        {"decided": _date(r["decided_at"]), "status": r["status"], "decision": r["text"], "reason": r["reason"],
         "services": ", ".join(r["services"]), "links": ", ".join(r["links"] or []),
         "applies_now": applies(r)["applies"], "applies_why": applies(r)["why"]}
        for r in rows
    ]
    last = out[0]
    summary = f"{len(out)} decision(s) about {target}. Latest ({last['decided']}): {last['status']}: {last['decision']}" + (
        f", reason: {last['reason']}" if last["reason"] else ""
    ) + "."
    live = [o for o in out if o["applies_now"]]
    summary += f" {len(live)} of them still apply to the current graph." if live else " None of them applies to the current graph any more."
    return Result(summary, out, ["decided", "status", "decision", "reason", "services", "applies_now"], ev)


@tool(
    "contradictions_for",
    "Contradictions",
    "Places where two of our own sources disagree about a service, package or advisory (Dockerfile vs go.mod toolchain, package.json vs lockfile, "
    "an advisory whose fixed version is not newer than the installed one, a public/internal label vs the ingress edges, a 'verified' decision whose "
    "exposures are still reachable). If any is open, say so and do not recommend a fix that depends on the disputed fact.",
    [
        Param("service", "string", "Service name (optional)"),
        Param("vuln", "string", "CVE/GHSA id (optional)"),
    ],
    "memory",
    {"service": "paymentservice"},
)
def contradictions_for(trace: Trace, service, vuln, graph_name=None):
    svc = resolve_service(trace, service, graph_name) if service else None
    vid = resolve_vulnerability(trace, vuln, graph_name) if vuln else None
    rows = trace.ro(
        """MATCH (x:Contradiction {status: 'open'}) WHERE ($s IS NULL OR x.service = $s) AND ($v IS NULL OR x.vuln = $v)
RETURN x.kind AS kind, x.detail AS detail, x.resolution AS resolution, x.sources_json AS sources, x.service AS service, x.vuln AS vuln
ORDER BY x.kind, x.detail LIMIT 25""",
        {"s": svc, "v": vid},
        graph_name,
    )
    target = " / ".join(x for x in [svc, vid] if x) or "the whole graph"
    if not rows:
        return Result(f"No open evidence contradiction about {target}: the sources Warden checked agree.", [], None, None)
    out = [{**r, "sources": "; ".join(json.loads(r["sources"] or "[]"))} for r in rows]
    return Result(f"{len(out)} open contradiction(s) about {target}. Do not rely on the disputed fact until resolved. First: {out[0]['detail']}", out,
                  ["kind", "detail", "resolution", "sources"], None)


@tool(
    "exposure_timeline",
    "Exposure timeline",
    "What happened over time to a service or an advisory: exposures opened and closed, dependency moves, service exposure changes, "
    "when the advisory was listed on CISA KEV, and decisions made or gone stale. A fixed advisory is reported as historical, never active.",
    [
        Param("service", "string", "Service name (optional)"),
        Param("vuln", "string", "CVE/GHSA id (optional)"),
        Param("limit", "integer", "How many events", default=20, minimum=1, maximum=100),
    ],
    "memory",
    {"vuln": "CVE-2023-44487"},
)
def exposure_timeline(trace: Trace, service, vuln, limit, graph_name=None):
    if not service and not vuln:
        raise ToolError("Give a service, a vulnerability, or both.")
    from warden import memory, timeline
    from warden.tools.security import best_findings, scored_paths

    svc = resolve_service(trace, service, graph_name) if service else None
    vid = resolve_vulnerability(trace, vuln, graph_name) if vuln else None
    ledger = trace.ro(
        """MATCH (e:TimelineEvent) WHERE ($s IS NULL OR e.service = $s) AND ($v IS NULL OR e.vuln = $v)
RETURN e.kind AS kind, e.at AS at, e.ref AS ref, e.service AS service, e.vuln AS vuln, e.detail AS detail, e.kev AS kev ORDER BY e.at DESC LIMIT 100""",
        {"s": svc, "v": vid},
        graph_name,
    )
    drows = trace.ro(
        """MATCH (d:Decision) WHERE ($v IS NULL OR (d)-[:ABOUT]->(:Vulnerability {id: $v})) AND ($s IS NULL OR (d)-[:CHANGES]->(:Service {name: $s}))
RETURN d.id AS id, d.status AS status, d.text AS text, d.reason AS reason, d.decided_at AS at ORDER BY d.decided_at DESC LIMIT 20""",
        {"s": svc, "v": vid},
        graph_name,
    )
    kev = None
    if vid:
        v = trace.ro("MATCH (v:Vulnerability {id: $v}) RETURN v.kev AS kev, v.kev_added AS added, v.kev_name AS name", {"v": vid}, graph_name)[0]
        if v["kev"]:
            kev = {"vuln": vid, "added": timeline.kev_added_ms(v["added"]), "name": v["name"]}
    stale = {}
    versions, sha = memory.current_versions(), memory.ingest_sha()
    for d in memory.decisions():
        if d["id"] in {r["id"] for r in drows}:
            st = memory.applies_now(d, versions, sha)
            if st["state"] in ("stale", "done_or_changed", "superseded", "expired"):
                stale[d["id"]] = st["why"]
    events = timeline.merge_events(ledger, drows, kev, None, stale)[:limit]
    findings = best_findings(scored_paths(trace, graph_name=graph_name))
    active = [f for f in findings if (not vid or f["vuln"] == vid) and (not svc or f["service"] == svc)]
    closed = [e for e in ledger if e["kind"] == "exposure_closed"]
    if vid:
        state = "active" if active else ("historical" if closed else "not reachable")
        head = f"{vid} is {state}: {len(active)} reachable exposure(s) now, {len(closed)} closed over the recorded history."
    else:
        head = f"{svc}: {len(active)} reachable exposure(s) now, {len(closed)} closed and {sum(1 for e in ledger if e['kind'] == 'exposure_opened')} opened in the recorded history."
    rows = [{"when": _date(e["at"]), "kind": e["kind"], "what": e["detail"]} for e in events]
    if not rows:
        return Result(head + " No events recorded yet (history starts at the first sync).", [], None, None)
    return Result(head + f" Latest: {rows[0]['kind']}: {rows[0]['what']}.", rows, ["when", "kind", "what"], None)
