"""One place that turns analysis into pending approvals, used by the API, the chat agent and the watcher.

Every proposal passes the same guards: a fix plan must clear the rehearsal gate (the graph copy proves risk
drops and nothing new and critical appears), and the same proposal is never filed twice while one is pending.
"""
from warden.actions import approvals, patches


def pending_keys() -> set[str]:
    return {a["payload"].get("dedupe_key") for a in approvals.list_all() if a["status"] == "pending" and a["payload"].get("dedupe_key")}


def file_fix_plan(plan: dict, requested_by: str, trigger: dict | None = None, dedupe_key: str | None = None) -> tuple[dict | None, str | None]:
    """Returns (approval, blocked_reason). `trigger` explains why this was proposed (shown on the card)."""
    if not plan.get("items"):
        return None, plan.get("summary") or "Nothing to upgrade."
    gate = plan.get("gate") or {"passed": True, "checks": []}
    if not gate["passed"]:
        failed = "; ".join(f"{c['check']} ({c['detail']})" for c in gate["checks"] if not c["ok"] and c.get("level", "block") == "block")
        return None, f"Rehearsal gate blocked this plan: {failed}"
    if dedupe_key and dedupe_key in pending_keys():
        return None, "An identical proposal is already waiting for approval."
    for it in plan["items"]:
        it["major"] = patches.major_bump(it["from"], it["to"])
    payload = {k: v for k, v in plan.items() if k != "queries"}
    payload["patches"] = patches.build_patches(plan["items"])
    payload["trigger"] = trigger
    payload["dedupe_key"] = dedupe_key
    n = len(plan["items"])
    kev = " (covers every CISA KEV path)" if plan["after"]["kev_findings"] == 0 and plan["before"]["kev_findings"] else ""
    title = f"Upgrade {n} package{'s' if n != 1 else ''} across {len(payload['patches'])} services{kev}"
    return approvals.create("fix_plan", title, plan["summary"], payload, requested_by=requested_by), None


def file_issue(title: str, body: str, services: list[str], trigger: dict, requested_by: str, dedupe_key: str) -> tuple[dict | None, str | None]:
    if dedupe_key in pending_keys():
        return None, "An identical proposal is already waiting for approval."
    payload = {"title": title, "body": body, "labels": ["warden"], "services": services, "trigger": trigger, "dedupe_key": dedupe_key, "summary": body.split("\n")[0]}
    return approvals.create("issue", title, payload["summary"], payload, requested_by=requested_by), None
