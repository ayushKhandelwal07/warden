"""Entity resolution shared by tools. A name the graph doesn't know is an explicit error ("not in the graph"),
never an empty answer that looks like "nothing breaks"."""
import difflib

from warden.tools.base import ToolError, Trace


def resolve_service(trace: Trace, name: str, graph_name: str | None = None) -> str:
    rows = trace.ro("MATCH (s:Service) RETURN s.name AS name ORDER BY name", graph_name=graph_name)
    names = [r["name"] for r in rows]
    key = name.strip().lower()
    if key in names:
        return key
    # "checkout" -> checkoutservice; a typo one letter off still resolves; anything vaguer is an error.
    starts = [n for n in names if n.startswith(key) or n == f"{key}service"]
    if len(starts) == 1:
        return starts[0]
    close = difflib.get_close_matches(key, names, n=1, cutoff=0.88)
    if close:
        return close[0]
    raise ToolError(f"Service '{name}' is not in the graph. Known services: {', '.join(names)}")


def resolve_vulnerability(trace: Trace, vuln: str, graph_name: str | None = None) -> str:
    v = vuln.strip().upper()
    rows = trace.ro(
        "MATCH (x:Vulnerability) WHERE toUpper(x.id) = $v OR any(a IN x.aliases WHERE toUpper(a) = $v) RETURN x.id AS id LIMIT 1",
        {"v": v},
        graph_name,
    )
    if not rows:
        raise ToolError(f"Vulnerability '{vuln}' is not in the graph (no package in the demo org is affected by it).")
    return rows[0]["id"]
