"""Entity search: turns free text into graph nodes (full-text index), the agent's entry point."""
import re

from warden.tools.base import Param, Result, ToolError, Trace, tool

LABELS = ["Service", "Package", "Vulnerability", "Person", "PullRequest"]


@tool(
    "find_entity",
    "Find entity",
    "Full-text search over services, packages, vulnerabilities, people and pull requests (FalkorDB full-text "
    "indexes; exact match for CVE/GHSA ids). Use it to turn a name in a question into a graph node.",
    [
        Param("text", "string", "What to look for", required=True),
        Param("label", "enum", "Limit to one kind of node", default="any", choices=["any", *LABELS]),
    ],
    "search",
    {"text": "checkout"},
)
def find_entity(trace: Trace, text, label, graph_name=None):
    if re.match(r"^(CVE|GHSA|GO|PYSEC)-", text, re.I):
        rows = trace.ro(
            """MATCH (v:Vulnerability) WHERE toUpper(v.id) = $t OR any(a IN v.aliases WHERE toUpper(a) = $t)
RETURN 'Vulnerability' AS label, v.id AS name, v.summary AS detail, 1.0 AS score""",
            {"t": text.upper()},
            graph_name,
        )
    else:
        tokens = [t for t in re.split(r"[^A-Za-z0-9]+", text) if t]
        if not tokens:
            raise ToolError("Search text needs at least one letter or digit.")
        q = " ".join(f"{t}*" for t in tokens)
        rows = []
        for lab in LABELS if label == "any" else [label]:
            name_expr = {
                "Service": "node.name", "Package": "node.key", "Vulnerability": "node.id",
                "Person": "node.name", "PullRequest": "'#' + toString(node.number)",
            }[lab]
            detail_expr = {
                "Service": "node.description", "Package": "node.ecosystem", "Vulnerability": "node.summary",
                "Person": "node.login", "PullRequest": "node.title",
            }[lab]
            rows += trace.ro(
                f"""CALL db.idx.fulltext.queryNodes('{lab}', $q) YIELD node, score
RETURN '{lab}' AS label, {name_expr} AS name, {detail_expr} AS detail, score ORDER BY score DESC LIMIT 5""",
                {"q": q},
                graph_name,
            )
        # Full-text scores aren't comparable across indexes: prefer the kind of node a question usually means.
        rows.sort(key=lambda r: (LABELS.index(r["label"]), -r["score"]))
    if not rows:
        return Result(f"Nothing in the graph matches '{text}'.", [], None, None)
    top = rows[0]
    return Result(f"Best match for '{text}': {top['label']} {top['name']}.", rows[:12], ["label", "name", "detail", "score"], None)
