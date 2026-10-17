"""People tools: who owns a service and who has actually worked on it (from real commit history)."""
from datetime import datetime, timezone

from warden.graph.evidence import Evidence
from warden.tools.base import Param, Result, Trace, tool
from warden.tools.common import resolve_service


def _date(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d") if ms else None


@tool(
    "who_owns",
    "Who owns",
    "The team that owns a service, and the GitHub handles allowed as reviewers on the fork.",
    [Param("service", "string", "Service name", required=True)],
    "people",
    {"service": "checkoutservice"},
)
def who_owns(trace: Trace, service, graph_name=None):
    svc = resolve_service(trace, service, graph_name)
    rows = trace.ro(
        """MATCH p = (s:Service {name: $s})-[:OWNED_BY]->(t:Team)
RETURN p, t.name AS team, t.slug AS slug, t.reviewers AS reviewers""",
        {"s": svc},
        graph_name,
    )
    if not rows:
        return Result(f"No team owns {svc} in the graph.", [], None, Evidence())
    ev = Evidence()
    for r in rows:
        ev.add_path(r["p"])
    out = [{"team": r["team"], "slug": r["slug"], "reviewers": ", ".join(r["reviewers"] or []) or "none configured"} for r in rows]
    return Result(f"{svc} is owned by the {out[0]['team']} team.", out, None, ev, sources=["org/teams.yaml (curated)"])


@tool(
    "who_knows",
    "Who knows",
    "People who have actually worked on a service, ranked from real commit history: commits that touched the "
    "service's files, weighted toward recent work. Each person comes with an example commit as proof. Use for "
    "'who should review this' and 'who knows X'.",
    [
        Param("service", "string", "Service name", required=True),
        Param("limit", "integer", "How many people", default=5, minimum=1, maximum=15),
    ],
    "people",
    {"service": "checkoutservice"},
)
def who_knows(trace: Trace, service, limit, graph_name=None):
    svc = resolve_service(trace, service, graph_name)
    latest = trace.ro("MATCH (c:Commit) RETURN max(c.authored_at) AS t", graph_name=graph_name)[0]["t"] or 0
    recent_cutoff = latest - 180 * 24 * 3600 * 1000
    rows = trace.ro(
        """MATCH (p:Person)-[k:KNOWS]->(s:Service {name: $s})
WITH p, k, k.commits * (CASE WHEN k.last_touched >= $recent THEN 1.5 ELSE 1.0 END) AS score
RETURN p.key AS key, p.name AS person, p.login AS login, k.commits AS commits, k.last_touched AS last_touched,
       round(score * 10) / 10 AS score
ORDER BY score DESC, commits DESC, person
LIMIT $n""",
        {"s": svc, "recent": recent_cutoff, "n": limit},
        graph_name,
    )
    if not rows:
        return Result(f"No commit history touches {svc} in the ingested window: nobody can be shown to know it.", [], None, Evidence())
    ev = Evidence()
    for r in rows[:3]:
        proof = trace.ro(
            """MATCH p = (:Person {key: $k})-[:AUTHORED]->(c:Commit)-[:TOUCHES]->(:File)-[:BELONGS_TO]->(:Service {name: $s})
RETURN p, c.message AS message ORDER BY c.authored_at DESC LIMIT 1""",
            {"k": r["key"], "s": svc},
            graph_name,
        )
        if proof:
            ev.add_path(proof[0]["p"])
            r["example_commit"] = proof[0]["message"][:90]
    out = [
        {"person": r["person"], "login": r["login"], "commits": r["commits"], "last_touched": _date(r["last_touched"]),
         "score": r["score"], "example_commit": r.get("example_commit")}
        for r in rows
    ]
    top = out[0]
    summary = f"{top['person']} knows {svc} best: {top['commits']} commits, last on {top['last_touched']}." + (
        f" Next: {', '.join(o['person'] for o in out[1:3])}." if len(out) > 1 else ""
    )
    return Result(summary, out, ["person", "commits", "last_touched", "score", "example_commit"], ev)
