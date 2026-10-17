"""Change tools: what a pull request touched."""
from warden.graph.evidence import Evidence
from warden.tools.base import Param, Result, ToolError, Trace, tool


@tool(
    "pr_touched_services",
    "PR touched services",
    "Which services a pull request changed, via PullRequest → Commit → File → Service, with the files per service.",
    [Param("pr", "integer", "Pull request number", required=True, minimum=1, maximum=100000)],
    "changes",
    {"pr": 1840},
)
def pr_touched_services(trace: Trace, pr, graph_name=None):
    head = trace.ro("MATCH (p:PullRequest {number: $n}) RETURN p.title AS title, p.url AS url", {"n": pr}, graph_name)
    if not head:
        raise ToolError(f"PR #{pr} is not in the graph (only merged PRs from the ingested history are).")
    rows = trace.ro(
        """MATCH (pr:PullRequest {number: $n})-[:CONTAINS]->(:Commit)-[:TOUCHES]->(f:File)
OPTIONAL MATCH (f)-[:BELONGS_TO]->(s:Service)
RETURN coalesce(s.name, '(no service)') AS service, collect(DISTINCT f.path) AS files
ORDER BY service""",
        {"n": pr},
        graph_name,
    )
    ev = Evidence()
    for p in trace.ro(
        """MATCH p = (pr:PullRequest {number: $n})-[:CONTAINS]->(:Commit)-[:TOUCHES]->(:File)-[:BELONGS_TO]->(:Service)
RETURN p LIMIT 12""",
        {"n": pr},
        graph_name,
    ):
        ev.add_path(p["p"])
    services = [r["service"] for r in rows if r["service"] != "(no service)"]
    out = [{"service": r["service"], "files": len(r["files"]), "paths": ", ".join(r["files"][:4]) + (" …" if len(r["files"]) > 4 else "")} for r in rows]
    summary = f"PR #{pr} \"{head[0]['title']}\" touches " + (
        f"{len(services)} service(s): {', '.join(services)}." if services else "no service code (repo-wide files only)."
    )
    return Result(summary, out, None, ev, sources=[head[0]["url"]])
