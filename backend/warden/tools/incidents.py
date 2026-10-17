"""Incident history: what went wrong before on these services, and whether it was the same kind of change."""
import re

from warden.graph.evidence import Evidence
from warden.tools.base import Param, Result, Trace, tool
from warden.tools.common import resolve_service


def _name_tokens(x: str | None) -> set[str]:
    """Tokens of a package's own name (last path / artifact segment): 'google.golang.org/grpc' -> {grpc},
    'com.google.api.grpc:proto-google-common-protos' -> {proto, google, common, protos}."""
    last = re.split(r"[/:]", (x or "").lower().lstrip("@"))[-1]
    return {t for t in re.split(r"[^a-z0-9]+", last) if len(t) > 3 or t == "grpc"}


def _same_change(package: str | None, trigger: str | None) -> bool:
    """'opentelemetry-js' matches '@opentelemetry'; a Java proto artifact does not match grpc-go."""
    a, b = _name_tokens(package), _name_tokens(trigger)
    return bool(a and b and a & b)


@tool(
    "past_incidents",
    "Past incidents",
    "Incidents that affected the given services, newest first, flagging ones triggered by the same kind of change "
    "(e.g. the same package being upgraded). Incident history in the demo org is curated and synthetic.",
    [
        Param("services", "string[]", "Services to check", required=True),
        Param("package", "string", "Package being changed, to match incidents triggered by the same change (optional)"),
    ],
    "changes",
    {"services": ["frontend", "checkoutservice"], "package": "google.golang.org/grpc"},
)
def past_incidents(trace: Trace, services, package, graph_name=None):
    names = [resolve_service(trace, s, graph_name) for s in services]
    rows = trace.ro(
        """MATCH p = (i:Incident)-[:AFFECTED]->(s:Service) WHERE s.name IN $names
WITH i, collect(DISTINCT s.name) AS hit, collect(p) AS paths
OPTIONAL MATCH (i)-[:AFFECTED]->(other:Service)
RETURN i.id AS id, i.title AS title, i.occurred_at AS date, i.severity AS severity, i.summary AS summary,
       i.lesson AS lesson, i.trigger_kind AS trigger_kind, i.trigger_package AS trigger_package,
       hit AS affected_here, collect(DISTINCT other.name) AS affected_all, paths
ORDER BY date DESC""",
        {"names": names},
        graph_name,
    )
    ev = Evidence()
    out = []
    for r in rows:
        for p in r["paths"]:
            ev.add_path(p)
        same = _same_change(package, r["trigger_package"])
        out.append(
            {"incident": r["id"], "date": r["date"], "severity": r["severity"], "title": r["title"],
             "same_kind_of_change": same, "affected_here": ", ".join(r["affected_here"]), "lesson": r["lesson"],
             "trigger": f"{r['trigger_kind']}: {r['trigger_package']}"}
        )
    out.sort(key=lambda x: x["date"] or "", reverse=True)  # newest first...
    out.sort(key=lambda x: not x["same_kind_of_change"])  # ...but same-kind-of-change incidents on top (stable sort)
    if not out:
        return Result(f"No recorded incident affected {', '.join(names)}.", [], None, Evidence(), sources=["org/postmortems.yaml (curated, synthetic)"])
    same = [o for o in out if o["same_kind_of_change"]]
    summary = f"{len(out)} past incident(s) hit {', '.join(names)}" + (
        f"; {same[0]['incident']} was triggered by the same kind of change ({same[0]['trigger']}): {same[0]['lesson']}"
        if same
        else "."
    )
    return Result(summary, out, ["incident", "date", "severity", "title", "same_kind_of_change", "affected_here", "lesson"], ev,
                  sources=["org/postmortems.yaml (curated, synthetic)"])
