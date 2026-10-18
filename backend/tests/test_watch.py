"""Watcher, rehearsal gate, shared proposal filing and precise verification. No GitHub writes happen here."""
import json

import pytest

from warden import config, proposals, sync, watch
from warden.actions import approvals
from warden.graph.client import db, rw
from warden.planner import _gate

try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False

live = pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")


def nums(findings=10, kev=0, risk=100.0, by_key=None):
    return {"findings": findings, "kev_findings": kev, "risk": risk, "by_key": by_key or {}}


def test_gate_passes_when_risk_drops_and_nothing_new():
    g = _gate(nums(kev=2, risk=100), nums(kev=0, risk=40), [])
    assert g["passed"] and all(c["ok"] for c in g["checks"])


def test_gate_blocks_when_a_critical_finding_appears():
    after = nums(risk=40, by_key={("CVE-X", "frontend"): {"kev": False, "severity": "CRITICAL"}})
    g = _gate(nums(risk=100), after, [("CVE-X", "frontend")])
    assert not g["passed"] and "CVE-X on frontend" in [c for c in g["checks"] if not c["ok"]][0]["detail"]


def test_gate_blocks_when_risk_does_not_drop():
    assert not _gate(nums(risk=100), nums(risk=100), [])["passed"]


def test_gate_blocks_a_plan_that_leaves_kev_untouched():
    assert not _gate(nums(kev=2, risk=100), nums(kev=2, risk=50), [])["passed"]


def test_blocked_plan_is_never_filed():
    plan = {"items": [{"package": "p", "from": "1", "to": "2", "ecosystem": "npm", "services": [], "vulns": [], "changes": []}],
            "gate": {"passed": False, "checks": [{"check": "total risk drops", "ok": False, "detail": "10 → 10"}]}, "summary": "s"}
    approval, reason = proposals.file_fix_plan(plan, "watcher")
    assert approval is None and "Rehearsal gate blocked" in reason


@live
def test_duplicate_issue_proposals_are_not_filed_twice():
    key = "exposure:test-svc:abc"
    a, _ = proposals.file_issue("t", "body", ["frontend"], {"why": "x"}, "watcher", key)
    try:
        assert a and a["status"] == "pending"
        b, reason = proposals.file_issue("t", "body", ["frontend"], {"why": "x"}, "watcher", key)
        assert b is None and "already waiting" in reason
    finally:
        rw("MATCH (a:Approval {id: $id}) DELETE a", {"id": a["id"]}, approvals.agents_graph())


@live
def test_verification_uses_exact_targets_and_marks_decisions_verified():
    still = next(iter(sync._findings(config.org_graph_name())))  # a (vuln, service) that is reachable right now
    ids = {}
    for name, targets in {"gone": [["CVE-0000-0000", "frontend"]], "open": [list(still)]}.items():
        did = f"dec_test_{name}"
        ids[name] = did
        rw("CREATE (d:Decision {id: $id, status: 'approved', text: $n, targets_json: $t, source_type: 'test'})",
           {"id": did, "n": name, "t": json.dumps(targets)})
    try:
        res = {r["decision"]: r for r in sync.verify_decisions({})}
        assert res[ids["gone"]]["verified"] and res[ids["gone"]]["remaining"] == 0
        assert not res[ids["open"]]["verified"] and res[ids["open"]]["remaining"] == 1
    finally:
        rw("MATCH (d:Decision) WHERE d.source_type = 'test' DETACH DELETE d")


@live
def test_watcher_without_github_reports_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", None)
    res = watch.tick()
    assert res["ok"] is False and "GitHub" in res["status"]
    assert "not connected" in watch.state()["last_status"]


@live
def test_second_tick_is_refused_while_one_runs():
    assert watch._lock.acquire(blocking=False)
    try:
        assert watch.tick()["status"] == "A check is already running"
    finally:
        watch._lock.release()


def test_issue_approval_that_fails_stays_pending_with_a_clear_reason(monkeypatch):
    if not LIVE:
        pytest.skip("FalkorDB not reachable")
    monkeypatch.setattr(config, "GITHUB_TOKEN", "x")
    monkeypatch.setattr(config, "GITHUB_OWNER", "someone")

    def boom(_payload):
        raise RuntimeError("GitHub POST /repos/someone/x/issues → 410: Issues has been disabled")

    monkeypatch.setitem(approvals.EXECUTORS, "issue", boom)
    a = approvals.create("issue", "t", "s", {"title": "t", "body": "b", "services": []})
    try:
        out = approvals.approve(a["id"])
        assert out["status"] == "pending" and "Issues are turned off" in out["last_error"]
    finally:
        rw("MATCH (a:Approval {id: $id}) DELETE a", {"id": a["id"]}, approvals.agents_graph())
        rw("MATCH (d:Decision {approval_id: $id}) DETACH DELETE d", {"id": a["id"]})


def test_turning_the_watcher_on_does_not_rewrite_the_graph_until_the_fork_moves(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", "x")
    monkeypatch.setattr(config, "GITHUB_OWNER", "someone")
    head = {"sha": "aaaaaaa1111111"}
    monkeypatch.setattr(watch.github, "branch_head", lambda b: head["sha"])
    monkeypatch.setattr(watch.github, "list_prs", lambda *a, **k: [])
    synced = []
    monkeypatch.setattr(watch.sync, "sync_fork", lambda b: synced.append(b) or {"fixed": [], "new": [], "decisions": [], "exposure": {"added": []}, "worse": []})
    try:
        watch.set_enabled(True)
        assert watch.state()["last_head"] == "aaaaaaa1111111"
        assert watch.tick()["synced"] is False and synced == []  # the demo graph differs from the fork's commit, yet nothing is re-read
        head["sha"] = "bbbbbbb2222222"
        out = watch.tick()
        assert out["synced"] is True and synced == ["demo-base"] or synced == [config.GITHUB_BASE or "main"]
        assert watch.state()["last_head"] == "bbbbbbb2222222"
        assert watch.tick()["synced"] is False  # and it does not re-read again for the same commit
    finally:
        watch.set_enabled(False)
        rw("MATCH (e:WatchEvent) WHERE e.kind = 'watch' OR e.kind = 'sync' DELETE e", graph_name=watch._g())
        rw("MATCH (w:Watcher {id: 'main'}) REMOVE w.last_head", graph_name=watch._g())
