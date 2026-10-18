"""Closing the loop on a fix: proposed → approved → PR open → checks → merged → graph refreshed → path gone.

The last two steps are measured, not assumed: after the fork moves, the graph is re-read and the exact (advisory, service)
exposures the approval promised to remove are looked up again. The verdict is verified_fixed, partially_fixed or not_fixed.
"""
from warden import config, sync
from warden.actions import github


def verdict(targets: set[tuple], still: set[tuple], merged: bool, refreshed: bool) -> dict:
    """Pure state machine for the final step."""
    remaining = sorted(targets & still)
    gone = len(targets) - len(remaining)
    if not targets:
        state = "unknown"
    elif not merged:
        state = "waiting_for_merge"
    elif not refreshed:
        state = "waiting_for_graph"
    elif not remaining:
        state = "verified_fixed"
    elif gone:
        state = "partially_fixed"
    else:
        state = "not_fixed"
    return {"state": state, "targets": len(targets), "gone": gone, "remaining": [{"vuln": v, "service": s} for v, s in remaining]}


def _step(key: str, label: str, done: bool, detail: str, state: str | None = None) -> dict:
    return {"key": key, "label": label, "done": done, "detail": detail, "state": state or ("done" if done else "todo")}


def timeline(a: dict, prs: list[dict], checks: dict[int, dict], merged_numbers: set[int], refreshed: bool, still: set[tuple]) -> dict:
    p = a.get("payload") or {}
    targets = {(r["vuln"], r["service"]) for r in p.get("removed", [])}
    approved = a["status"] in ("approved", "approved_not_executed")
    pr_nums = [x["number"] for x in prs]
    all_merged = bool(pr_nums) and set(pr_nums) <= merged_numbers
    states = [checks[n]["state"] for n in pr_nums if n in checks]
    if "failure" in states:
        check_state = "failure"
    elif "pending" in states:
        check_state = "pending"
    elif states and all(s == "success" for s in states):
        check_state = "success"
    else:
        check_state = "none"
    v = verdict(targets, still, all_merged, refreshed)
    approved_detail = f"by {a['decided_by']}" if a.get("decided_by") else "waiting for a human"
    if a["status"] == "rejected":
        approved_detail = "rejected"
    check_detail = {"success": "all checks passed", "failure": "a check failed", "pending": "checks still running", "none": "no checks reported"}[check_state]
    steps = [
        _step("proposed", "Proposed", True, f"by {a.get('requested_by', 'planner')}"),
        _step("approved", "Approved", approved, approved_detail),
        _step("pr_open", "PRs opened", bool(prs), f"{len(prs)} PR(s) on the fork" if prs else "no PR yet (GitHub not connected, or not approved)"),
        _step("checks", "Checks", check_state == "success", check_detail, {"success": "done", "failure": "failed", "pending": "running"}.get(check_state, "todo")),
        _step("merged", "Merged", all_merged, f"{len(merged_numbers & set(pr_nums))} of {len(pr_nums)} PR(s) merged" if pr_nums else "nothing to merge"),
        _step("graph_refreshed", "Graph re-read", all_merged and refreshed, "the graph reflects the fork's current head" if refreshed else "the graph is older than the fork's head"),
        _step("path_gone", "Exposures gone", v["state"] == "verified_fixed",
              f"{v['gone']} of {v['targets']} promised exposures are gone" if v["targets"] else "this approval promised no exposures",
              "failed" if v["state"] in ("partially_fixed", "not_fixed") else None),
    ]
    return {"approval": a["id"], "steps": steps, "verdict": v, "checks": [{"pr": n, **checks[n]} for n in pr_nums if n in checks]}


def build(a: dict) -> dict:
    """Gathers live state (GitHub when connected, the graph always) and returns the timeline."""
    prs = (a.get("result") or {}).get("prs", [])
    checks: dict[int, dict] = {}
    merged: set[int] = set()
    refreshed = False
    if github.configured() and prs:
        try:
            ours = {x["number"] for x in prs}
            merged = {x["number"] for x in github.list_prs("all", 50) if x["merged"] and x["number"] in ours}
            for n in ours:
                checks[n] = github.pr_checks(n)
            refreshed = github.branch_head(config.GITHUB_BASE or "main") == sync.current_ref().get("sha")
        except Exception as e:  # GitHub being unreachable is shown, not hidden
            checks = {x["number"]: {"state": "none", "runs": [], "error": str(e)[:120]} for x in prs}
    still = {(f["vuln"], f["service"]) for f in sync._findings(config.org_graph_name()).values()}
    out = timeline(a, prs, checks, merged, refreshed, still)
    out["preflight"] = (a.get("payload") or {}).get("preflight")
    return out
