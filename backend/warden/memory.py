"""Decision memory that changes what Warden proposes.

Every approval and rejection is a Decision node that remembers which upgrades it concerned (package, from, to, services) and which
ingest it was made against. The planner reads them back:

  rejected   a recent rejection of the same upgrade removes that upgrade from the candidates, and the plan cites it
             (who, when, why). It stops applying once the package has moved to another version.
  approved   a prior approval is only reused while the situation is the same (package still at the version it was approved from,
             graph read from the same commit). Otherwise it is marked stale and the plan is re-gated, never trusted.

The deterministic gate still runs on every plan; memory only narrows which upgrades are proposed.
"""
import json
import time

from warden.graph.client import ro

REJECTION_DAYS = 90
DAY_MS = 86_400_000


def _now() -> int:
    return int(time.time() * 1000)


def items_of(payload: dict) -> list[dict]:
    """What a decision concerned: the upgrades in the plan (empty for issues and PR comments)."""
    return [{"package": i["package"], "from": str(i["from"]), "to": str(i["to"]), "services": i.get("services", []), "ecosystem": i.get("ecosystem")}
            for i in payload.get("items", [])]


def ingest_sha() -> str | None:
    rows, _ = ro("MATCH (r:IngestRun) RETURN r.sha AS sha ORDER BY r.at DESC LIMIT 1")
    return rows[0]["sha"] if rows else None


def current_versions() -> dict[str, dict[str, set[str]]]:
    """package name -> service -> versions now in the live graph."""
    rows, _ = ro("MATCH (s:Service)-[:DEPENDS_ON]->(p:Package) RETURN p.name AS name, s.name AS service, collect(DISTINCT p.version) AS versions")
    out: dict[str, dict[str, set[str]]] = {}
    for r in rows:
        out.setdefault(r["name"], {})[r["service"]] = {str(v) for v in r["versions"]}
    return out


def decisions() -> list[dict]:
    rows, _ = ro(
        """MATCH (d:Decision) WHERE d.items_json IS NOT NULL
        RETURN d.id AS id, d.status AS status, d.reason AS reason, d.decided_at AS at, d.decided_by AS by, d.text AS text,
               d.items_json AS items, d.ingest_sha AS sha ORDER BY d.decided_at DESC"""
    )
    return [{**r, "items": json.loads(r["items"] or "[]")} for r in rows]


def _stripv(v: str) -> str:
    return str(v).lstrip("v")


def applies_now(d: dict, versions: dict, sha: str | None, now: int | None = None, item: dict | None = None) -> dict:
    """Does this decision still describe today's situation? Pure given the inputs."""
    now = now or _now()
    items = [item] if item else d["items"]
    if not items:
        return {"applies": False, "state": "n/a", "why": "This decision did not concern a package upgrade."}
    still_at_from = []
    moved = []
    for it in items:
        here = {v for svc in it["services"] for v in versions.get(it["package"], {}).get(svc, set())} or {v for vs in versions.get(it["package"], {}).values() for v in vs}
        if _stripv(it["from"]) in {_stripv(v) for v in here}:
            still_at_from.append(it["package"])
        else:
            moved.append(it["package"])
    age_days = (now - (d["at"] or now)) // DAY_MS
    if d["status"] == "rejected":
        if age_days > REJECTION_DAYS:
            return {"applies": False, "state": "expired", "why": f"Rejected {age_days} days ago; rejections expire after {REJECTION_DAYS} days."}
        if not still_at_from:
            return {"applies": False, "state": "superseded", "why": f"{', '.join(moved)} is no longer at the version that was rejected; re-evaluate."}
        return {"applies": True, "state": "active", "why": f"Rejected {age_days} day(s) ago and {', '.join(still_at_from)} is still at the same version."}
    # approved (or approved but not executed / verified)
    if not still_at_from:
        return {"applies": False, "state": "done_or_changed", "why": f"{', '.join(moved)} has changed since; the approval no longer describes the live graph."}
    if d.get("sha") and sha and d["sha"] != sha:
        return {"applies": False, "state": "stale", "why": "The graph was re-read from a different commit after this approval; the plan will be re-gated, not reused."}
    return {"applies": True, "state": "fresh", "why": "Same package versions and the same graph commit as when it was approved."}


def adjust_candidates(paths: list[dict], sha: str | None = None) -> tuple[list[dict], list[dict]]:
    """Drops the scored paths of any package whose same upgrade was recently rejected. Returns (paths kept, notes citing decisions)."""
    versions = current_versions()
    ds = decisions()
    excluded: dict[str, dict] = {}
    notes: list[dict] = []
    for d in ds:
        for it in d["items"]:
            state = applies_now(d, versions, sha, item=it)
            note = {"decision": d["id"], "package": it["package"], "from": it["from"], "to": it["to"], "status": d["status"], "reason": d["reason"],
                    "by": d.get("by"), "at": d["at"], "state": state["state"], "why": state["why"]}
            if d["status"] == "rejected" and state["applies"]:
                key = next((p["package_key"] for p in paths if p["package_name"] == it["package"] and _stripv(str(p["version"])) == _stripv(it["from"])), None)
                if key and key not in excluded:
                    excluded[key] = note
                    notes.append({**note, "action": "excluded"})
            elif d["status"] != "rejected" and any(p["package_name"] == it["package"] for p in paths):
                notes.append({**note, "action": "reused" if state["applies"] else "re-gated"})
    return [p for p in paths if p["package_key"] not in excluded], notes
