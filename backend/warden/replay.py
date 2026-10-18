"""Investigation replay: re-run the tool calls behind a saved answer and say, per call, whether the graph still gives the same rows.

An answer is saved with the exact tool calls (name, arguments), their Cypher and their result rows, plus a snapshot stamp
(graph, ingest commit, graph write version, time). Replay re-runs every deterministic registry tool uncached against the
current graph (or the golden snapshot) and compares a digest of the rows:

  same           identical rows
  changed        rows differ; the added and removed rows are listed
  not_replayed   an action or rehearsal tool (it files approvals or copies the graph), so it is shown but not re-run
  error          the tool failed now (for example the entity no longer exists)
"""
import hashlib
import json
import time

from warden import config
from warden.tools import REGISTRY, run_tool

MAX_DIFF = 8


def digest(rows: list[dict]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()[:16]


def snapshot() -> dict:
    """Stamp saved with every answer: what the graph looked like when the answer was produced."""
    from warden import cache
    from warden.graph.client import ro

    try:
        run = ro("MATCH (r:IngestRun) RETURN r.ref AS ref, r.sha AS sha ORDER BY r.at DESC LIMIT 1")[0]
        run = run[0] if run else {}
    except Exception:
        run = {}
    return {"graph": config.org_graph_name(), "ref": run.get("ref"), "sha": run.get("sha"), "graph_version": cache.version(config.org_graph_name()), "at": int(time.time() * 1000)}


def _row_keys(rows: list[dict]) -> set[str]:
    return {json.dumps(r, sort_keys=True, default=str) for r in rows}


def compare(stored: dict, fresh: dict) -> dict:
    """Pure: stored result vs fresh result of the same tool call."""
    if fresh.get("error"):
        return {"status": "error", "error": fresh["error"]}
    a, b = stored.get("rows") or [], fresh.get("rows") or []
    da, db_ = digest(a), digest(b)
    out = {"status": "same" if da == db_ else "changed", "stored_digest": da, "now_digest": db_, "rows_before": len(a), "rows_after": len(b)}
    if da != db_:
        ka, kb = _row_keys(a), _row_keys(b)
        out["removed"] = [json.loads(x) for x in sorted(ka - kb)][:MAX_DIFF]
        out["added"] = [json.loads(x) for x in sorted(kb - ka)][:MAX_DIFF]
        out["summary_before"], out["summary_after"] = stored.get("summary"), fresh.get("summary")
    return out


def replay_events(events: list[dict], graph_name: str | None = None, run=run_tool) -> list[dict]:
    results = {e["id"]: e["result"] for e in events if e.get("type") == "tool_result"}
    calls = []
    for e in events:
        if e.get("type") != "tool_call":
            continue
        stored = results.get(e["id"]) or {}
        base = {"tool": e["tool"], "args": e.get("args") or {}, "queries": [{"cypher": q.get("cypher"), "ms": q.get("ms")} for q in stored.get("queries", [])],
                "summary": stored.get("summary"), "approval_id": stored.get("approval_id")}
        if e["tool"] not in REGISTRY:
            calls.append({**base, "status": "not_replayed", "why": "An action or rehearsal tool: it files an approval or copies the graph, so it is shown, not re-run."})
            continue
        fresh = run(e["tool"], e.get("args") or {}, graph_name, False)
        calls.append({**base, **compare(stored, fresh)})
    return calls


def replay_turn(data: dict, against: str = "current") -> dict:
    graph = config.golden_graph_name() if against == "golden" else None
    calls = replay_events(data.get("events", []), graph)
    ran = [c for c in calls if c["status"] != "not_replayed"]
    changed = [c for c in ran if c["status"] == "changed"]
    errors = [c for c in ran if c["status"] == "error"]
    reproduced = bool(ran) and not changed and not errors
    now = snapshot()
    if against == "golden":
        now = {**now, "graph": graph}
    return {
        "against": against, "saved": data.get("snapshot"), "now": now, "calls": calls, "reproduced": reproduced,
        "headline": ("Reproduced: every re-run tool call returns the same rows." if reproduced
                     else f"Changed since: {len(changed)} of {len(ran)} tool call(s) return different rows." if changed
                     else f"{len(errors)} tool call(s) failed now." if errors else "Nothing to re-run: this answer used only action tools."),
    }
