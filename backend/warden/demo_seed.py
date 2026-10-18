"""Labelled demo history, so a first-time reviewer sees what Warden does over time instead of empty lists.

Three records, all tagged payload.demo = true and shown as "demo history" in the UI:
  rejected  an upgrade a reviewer rejected with a reason (it then changes the next plan, via decision memory)
  pending   a real, rehearsed fix plan waiting for approval, with its gate result (built after the rejection, so it cites it)
  verified  a past fix whose exposures were confirmed gone after the merge (no targets, so it never contradicts the live graph)

Idempotent: a record that already exists is left alone. Nothing here talks to GitHub.
"""
from warden import planner, proposals
from warden.actions import approvals
from warden.graph.client import rw
from warden.tools.base import Trace
from warden.tools.security import scored_paths

REJECT_REASON = "A gRPC bump broke checkout in staging last week; revisit after the next release."


def _existing() -> dict[str, dict]:
    return {a["payload"].get("demo_kind"): a for a in approvals.list_all() if (a.get("payload") or {}).get("demo")}


def _grpc_item(paths: list[dict]) -> dict | None:
    cands = planner._candidates([p for p in paths if p["package_name"] == "google.golang.org/grpc"])
    return cands[0] if cands else None


def _mark(plan: dict, kind: str) -> dict:
    return {**plan, "demo": True, "demo_kind": kind}


def seed() -> dict:
    have = _existing()
    made = []
    if "rejected" not in have:
        cand = _grpc_item(scored_paths(Trace()))
        if cand:
            plan = planner.build_plan(1, chosen_override=[{**cand, "reason": "demo history", "risk_removed": 0.0}])
            if plan.get("items"):
                a = approvals.create("fix_plan", "Upgrade google.golang.org/grpc (demo history)", plan["summary"],
                                     {k: v for k, v in _mark(plan, "rejected").items() if k != "queries"}, requested_by="planner")
                approvals.reject(a["id"], REJECT_REASON, by="Demo reviewer")
                made.append("rejected")
    if "pending" not in have:
        plan = _mark(planner.build_plan(5), "pending")
        a, why = proposals.file_fix_plan(plan, "planner", {"why": "Demo history: the default fix plan, rehearsed and waiting for approval"}, "demo:pending")
        if a:
            made.append("pending")
    if "verified" not in have:
        payload = {"items": [], "patches": [], "removed": [], "demo": True, "demo_kind": "verified",
                   "before": None, "after": None, "summary": "Past fix, confirmed after the merge: every exposure it targeted was gone from the re-read graph."}
        a = approvals.create("fix_plan", "Upgrade lodash in paymentservice (demo history)", payload["summary"], payload, requested_by="planner")
        approvals.record_decision(a, "approved", reason=None, links=[], by="Demo reviewer")
        rw("MATCH (d:Decision {approval_id: $id}) SET d.status = 'verified', d.verified_at = timestamp()", {"id": a["id"]})
        approvals._finish(a["id"], "approved", {"executed": False, "reason": "Demo history: no GitHub action was taken."}, "Demo reviewer")
        made.append("verified")
    return {"created": made, "existing": sorted(k for k in have if k)}
