"""Topology tools: what depends on what, how things connect, and which nodes matter most (graph algorithms)."""
from warden.graph.evidence import Evidence
from warden.tools.base import Param, Result, ToolError, Trace, tool
from warden.tools.common import resolve_service


@tool(
    "blast_radius",
    "Blast radius",
    "Services affected if this service changes or goes down: everything that calls it, directly or through other "
    "services, up to `depth` hops, with the shortest path for each and whether that dependent faces the internet. "
    "Compare depth 1 with depth 3 to see hidden dependents.",
    [
        Param("service", "string", "The changed or failing service", required=True),
        Param("depth", "integer", "How many CALLS hops to follow", default=3, minimum=1, maximum=4),
    ],
    "topology",
    {"service": "paymentservice", "depth": 3},
)
def blast_radius(trace: Trace, service, depth, graph_name=None):
    svc = resolve_service(trace, service, graph_name)
    # Variable-length bounds can't be parameters in FalkorDB; `depth` is validated (1-4) before templating.
    cypher = f"""
MATCH p = (dep:Service)-[:CALLS*1..{depth}]->(s:Service {{name: $s}})
WITH dep, min(length(p)) AS hops
OPTIONAL MATCH (dep)-[:EXPOSED_VIA]->(ing:Ingress)
OPTIONAL MATCH (dep)-[:OWNED_BY]->(t:Team)
RETURN dep.name AS service, hops, ing IS NOT NULL AS internet_facing, ing.name AS ingress, t.name AS team
ORDER BY hops, service"""
    rows = trace.ro(cypher, {"s": svc}, graph_name)
    ev = Evidence()
    if rows:
        paths = trace.ro(
            f"MATCH p = (dep:Service)-[:CALLS*1..{depth}]->(s:Service {{name: $s}}) WITH dep, p ORDER BY length(p) "
            "WITH dep, collect(p)[0] AS p RETURN p",
            {"s": svc},
            graph_name,
        )
        maxlen = max(len(r["p"].nodes()) for r in paths)
        for r in paths:
            n = len(r["p"].nodes())
            # Align every path so the changed service sits in the right-most column.
            ev.add_path(r["p"], orders=[maxlen - n + i for i in range(n)])
        exposed = trace.ro(
            f"""MATCH (dep:Service)-[:CALLS*1..{depth}]->(:Service {{name: $s}})
            MATCH p = (:Internet)-[:REACHES]->(:Ingress)<-[:EXPOSED_VIA]-(dep) RETURN DISTINCT p""",
            {"s": svc},
            graph_name,
        )
        for r in exposed:
            dep_id = f"n{r['p'].nodes()[-1].id}"
            base = ev.nodes.get(dep_id, {}).get("order", 2)
            ev.add_path(r["p"], orders=[base - 2, base - 1, base])
        target = trace.ro("MATCH (s:Service {name: $s}) RETURN s", {"s": svc}, graph_name)[0]["s"]
        ev.add_node(target, maxlen - 1)
    public = [r["service"] for r in rows if r["internet_facing"]]
    if not rows:
        summary = f"Nothing calls {svc} within {depth} hop(s): a change to it has no service blast radius in the graph."
    else:
        summary = (
            f"{len(rows)} service(s) depend on {svc} within {depth} hop(s)"
            + (f"; internet-facing: {', '.join(public)}" if public else "; none of them face the internet")
            + f". Nearest: {', '.join(r['service'] for r in rows if r['hops'] == rows[0]['hops'])} ({rows[0]['hops']} hop)."
        )
    return Result(summary, rows, ["service", "hops", "internet_facing", "team"], ev)


@tool(
    "path_between",
    "Path between",
    "Shortest connection between two services, or from a service to a data asset (e.g. CardData), using "
    "FalkorDB's algo.SPpaths / shortestPath. Answers 'how is X connected to Y'.",
    [
        Param("source", "string", "Start service", required=True),
        Param("target", "string", "Target service or data asset name", required=True),
    ],
    "topology",
    {"source": "frontend", "target": "CardData"},
)
def path_between(trace: Trace, source, target, graph_name=None):
    src = resolve_service(trace, source, graph_name)
    data = trace.ro("MATCH (d:DataAsset {name: $t}) RETURN d.name AS name", {"t": target}, graph_name)
    if data:
        cypher = """MATCH (a:Service {name: $a}), (b:DataAsset {name: $b})
RETURN shortestPath((a)-[:CALLS|READS*..6]->(b)) AS p"""
        rows = trace.ro(cypher, {"a": src, "b": target}, graph_name)
        paths = [r["p"] for r in rows if r["p"] is not None]
    else:
        dst = resolve_service(trace, target, graph_name)
        cypher = """MATCH (a:Service {name: $a}), (b:Service {name: $b})
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['CALLS'], maxLen: 6, pathCount: 3})
YIELD path, pathWeight
RETURN path AS p, pathWeight AS hops ORDER BY hops"""
        rows = trace.ro(cypher, {"a": src, "b": dst}, graph_name)
        paths = [r["p"] for r in rows]
        target = dst
    if not paths:
        return Result(f"No CALLS path from {src} to {target} in the graph: {src} cannot reach it.", [], None, Evidence())
    ev = Evidence()
    out = []
    for p in paths:
        ev.add_path(p)
        out.append({"path": " → ".join(str(n.properties.get("name")) for n in p.nodes()), "hops": len(p.edges())})
    summary = f"{src} reaches {target} in {out[0]['hops']} hop(s): {out[0]['path']}" + (
        f" ({len(out)} shortest routes)" if len(out) > 1 else ""
    )
    return Result(summary, out, None, ev)


@tool(
    "rank",
    "Rank (graph algorithms)",
    "Graph algorithms as a tool. `betweenness` finds choke-point services that sit on the most call paths "
    "(exact, from all-pairs algo.SPpaths over CALLS). `pagerank` finds the most load-bearing packages in the dependency web "
    "(algo.pageRank over REQUIRES), combined with how many services ship each one.",
    [
        Param("algorithm", "enum", "Which algorithm", default="betweenness", choices=["betweenness", "pagerank"]),
        Param("limit", "integer", "How many results", default=8, minimum=1, maximum=30),
    ],
    "topology",
    {"algorithm": "betweenness"},
)
def rank(trace: Trace, algorithm, limit, graph_name=None):
    if algorithm == "betweenness":
        # Exact betweenness from all-pairs shortest paths (algo.SPpaths). FalkorDB's algo.betweenness samples
        # source nodes, which is unstable on a 12-service graph; this is exact and deterministic.
        rows = trace.ro(
            """MATCH (a:Service), (b:Service) WHERE a <> b
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['CALLS'], maxLen: 10, pathCount: 0}) YIELD path
WITH a, b, collect(path) AS paths
WITH a, b, paths, size(paths) AS total
UNWIND paths AS p
UNWIND nodes(p)[1..-1] AS v
WITH a, b, total, v, count(*) AS through
RETURN v.name AS service, sum(toFloat(through) / total) AS score ORDER BY score DESC, service""",
            graph_name=graph_name,
        )
        rows = rows[:limit]
        top = [r for r in rows if r["score"] > 0]
        summary = (
            "Choke points (services on the most call paths): " + ", ".join(f"{r['service']} ({r['score']:.0f})" for r in top[:3])
            if top
            else "No service sits between others on call paths."
        )
        return Result(summary, rows, ["service", "score"], None)
    rows = trace.ro(
        """CALL algo.pageRank('Package', 'REQUIRES') YIELD node, score
WITH node, score ORDER BY score DESC LIMIT $n
OPTIONAL MATCH (s:Service)-[:DEPENDS_ON]->(node)
OPTIONAL MATCH (node)-[:AFFECTED_BY]->(v:Vulnerability)
RETURN node.key AS package, round(score * 10000) / 10000 AS pagerank, count(DISTINCT s) AS services,
       count(DISTINCT v) AS vulnerabilities
ORDER BY pagerank DESC, package""",
        {"n": limit},
        graph_name,
    )
    if not rows:
        raise ToolError("The REQUIRES graph is empty; run the ingest first.")
    summary = "Most load-bearing packages (PageRank over REQUIRES): " + ", ".join(r["package"] for r in rows[:3]) + "."
    return Result(summary, rows, ["package", "pagerank", "services", "vulnerabilities"], None)
