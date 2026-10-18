"""Temporal view of the security graph: what changed, when, and why.

The live graph always describes *now* (a fixed vulnerability is gone from it, never shown as active). History lives in two places:
  - a ledger of TimelineEvent nodes written at every sync from the diff between the old and new graph (exposure opened or closed,
    service exposed or unexposed, dependency moved, call added or removed), each stamped with the ref and commit it was seen at;
  - the Decision nodes (made, verified, stale) and the CISA KEV listing date on the Vulnerability.
`events()` merges them, newest first. Incidents and past decisions are historical facts and are never rewritten.
"""
import calendar
import time
import uuid

from warden.graph.client import ro, rw, unwind

MAX_PER_SYNC = 300


def _ev(kind: str, at: int, ref: str | None, sha: str | None, **kw) -> dict:
    return {"id": f"ev_{uuid.uuid4().hex[:10]}", "kind": kind, "at": at, "ref": ref, "sha": sha, "service": kw.get("service"), "vuln": kw.get("vuln"),
            "package": kw.get("package"), "detail": kw["detail"], "kev": bool(kw.get("kev"))}


def from_diff(diff: dict, ref: str | None, sha: str | None, at: int | None = None) -> list[dict]:
    """Pure: turn a graph diff into ledger events."""
    at = at or int(time.time() * 1000)
    out = []
    for f in diff.get("fixed", []):
        out.append(_ev("exposure_closed", at, ref, sha, service=f["service"], vuln=f["vuln"], package=f.get("package"), kev=f.get("kev"),
                       detail=f"{f['vuln']} is no longer reachable in {f['service']}"))
    for f in diff.get("new", []):
        out.append(_ev("exposure_opened", at, ref, sha, service=f["service"], vuln=f["vuln"], package=f.get("package"), kev=f.get("kev"),
                       detail=f"{f['vuln']} became reachable in {f['service']} ({f.get('hops', '?')} hops)"))
    for e in diff.get("exposure", {}).get("added", []):
        out.append(_ev("service_exposed", at, ref, sha, service=e.split(" via ")[0], detail=f"{e} (now internet-facing)"))
    for e in diff.get("exposure", {}).get("removed", []):
        out.append(_ev("service_unexposed", at, ref, sha, service=e.split(" via ")[0], detail=f"{e} (no longer internet-facing)"))
    for m in diff.get("dependencies", {}).get("moves", []):
        for s in m["services"]:
            out.append(_ev("dependency_changed", at, ref, sha, service=s, detail=m["change"]))
    for c in diff.get("calls", {}).get("added", []):
        out.append(_ev("call_added", at, ref, sha, service=c.split(" → ")[0], detail=f"new call {c}"))
    for c in diff.get("calls", {}).get("removed", []):
        out.append(_ev("call_removed", at, ref, sha, service=c.split(" → ")[0], detail=f"call removed {c}"))
    return out[:MAX_PER_SYNC]


def record(diff: dict, ref: str | None, sha: str | None, graph_name: str | None = None) -> int:
    rows = from_diff(diff, ref, sha)
    if rows:
        unwind(
            """MERGE (e:TimelineEvent {id: row.id}) SET e.kind = row.kind, e.at = row.at, e.ref = row.ref, e.sha = row.sha, e.service = row.service,
            e.vuln = row.vuln, e.package = row.package, e.detail = row.detail, e.kev = row.kev, e.source_type = 'sync'""",
            rows, graph_name,
        )
    return len(rows)


def merge_events(ledger: list[dict], decisions: list[dict], kev: dict | None, state: str | None, now_stale: dict[str, str] | None = None) -> list[dict]:
    """Pure: one newest-first list from the ledger, decisions (with stale ones flagged) and the KEV listing."""
    out = [{"at": e["at"], "kind": e["kind"], "detail": e["detail"], "service": e["service"], "vuln": e["vuln"], "ref": e["ref"], "kev": e["kev"]} for e in ledger]
    for d in decisions:
        out.append({"at": d["at"], "kind": f"decision_{d['status']}", "detail": d["text"] + (f" ({d['reason']})" if d.get("reason") else ""), "service": None, "vuln": None, "ref": None, "kev": False})
        if now_stale and d["id"] in now_stale:
            out.append({"at": d["at"], "kind": "decision_stale", "detail": now_stale[d["id"]], "service": None, "vuln": None, "ref": None, "kev": False})
    if kev and kev.get("added"):
        out.append({"at": kev["added"], "kind": "kev_listed", "detail": f"{kev['vuln']} added to CISA KEV ({kev.get('name') or 'catalog entry'})", "service": None, "vuln": kev["vuln"], "ref": None, "kev": True})
    return sorted(out, key=lambda e: (-(e["at"] or 0), e["kind"]))


def kev_added_ms(date: str | None) -> int | None:
    try:
        return int(calendar.timegm(time.strptime(str(date)[:10], "%Y-%m-%d")) * 1000)
    except (TypeError, ValueError):
        return None


def ledger(service: str | None = None, vuln: str | None = None, limit: int = 60) -> list[dict]:
    rows, _ = ro(
        """MATCH (e:TimelineEvent) WHERE ($s IS NULL OR e.service = $s) AND ($v IS NULL OR e.vuln = $v)
        RETURN e.id AS id, e.kind AS kind, e.at AS at, e.ref AS ref, e.sha AS sha, e.service AS service, e.vuln AS vuln,
               e.package AS package, e.detail AS detail, e.kev AS kev ORDER BY e.at DESC LIMIT $n""",
        {"s": service, "v": vuln, "n": limit},
    )
    return rows
