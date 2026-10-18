"""Check parsing, pre-flight step selection and the verification state machine (pure), plus the endpoints on a seeded approval."""
import pytest
from fastapi.testclient import TestClient

from warden import verification
from warden.actions import approvals, github, preflight
from warden.graph.client import db, rw


def test_parse_checks_states():
    run = lambda s, c: {"name": "ci", "status": s, "conclusion": c, "html_url": "u"}  # noqa: E731
    assert github.parse_checks({"check_runs": []}, {"statuses": []})["state"] == "none"
    assert github.parse_checks({"check_runs": [run("completed", "success")]}, {})["state"] == "success"
    assert github.parse_checks({"check_runs": [run("completed", "success"), run("in_progress", None)]}, {})["state"] == "pending"
    assert github.parse_checks({"check_runs": [run("completed", "failure"), run("in_progress", None)]}, {})["state"] == "failure"
    assert github.parse_checks({}, {"statuses": [{"context": "build", "state": "error"}]})["state"] == "failure"


def test_preflight_steps_follow_the_changed_files():
    assert [s[0] for s in preflight.steps_for(["src/x/go.mod"])] == ["go mod tidy", "go build ./..."]
    assert preflight.steps_for(["src/y/package.json"])[0][2] == "npm"
    assert preflight.steps_for(["src/z/Dockerfile"])[0][1] == []


def test_verdict_state_machine():
    t = {("V1", "a"), ("V2", "a")}
    assert verification.verdict(t, set(), False, False)["state"] == "waiting_for_merge"
    assert verification.verdict(t, set(), True, False)["state"] == "waiting_for_graph"
    assert verification.verdict(t, set(), True, True)["state"] == "verified_fixed"
    assert verification.verdict(t, {("V1", "a")}, True, True)["state"] == "partially_fixed"
    assert verification.verdict(t, t, True, True)["state"] == "not_fixed"
    assert verification.verdict(set(), set(), True, True)["state"] == "unknown"


def test_timeline_marks_steps_in_order():
    a = {"id": "apr_x", "status": "approved", "decided_by": "Dev", "requested_by": "planner", "payload": {"removed": [{"vuln": "V1", "service": "a"}]}}
    prs = [{"number": 7}]
    open_pr = verification.timeline(a, prs, {7: {"state": "pending", "runs": []}}, set(), False, {("V1", "a")})
    assert [s["done"] for s in open_pr["steps"]] == [True, True, True, False, False, False, False]
    assert open_pr["steps"][3]["state"] == "running" and open_pr["verdict"]["state"] == "waiting_for_merge"
    closed = verification.timeline(a, prs, {7: {"state": "success", "runs": []}}, {7}, True, set())
    assert all(s["done"] for s in closed["steps"]) and closed["verdict"]["state"] == "verified_fixed"


try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False


@pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")
def test_endpoints_on_a_seeded_approval(monkeypatch):
    from warden.api import app as api

    from tests.test_api import _signup

    c = TestClient(api.app)
    _signup(c)
    a = approvals.create("fix_plan", "seeded", "s", {"items": [], "patches": [], "removed": [{"vuln": "CVE-2023-44487", "service": "frontend"}]})
    try:
        v = c.get(f"/api/approvals/{a['id']}/verification").json()
        assert v["steps"][0]["done"] and not v["steps"][1]["done"] and v["verdict"]["state"] == "waiting_for_merge"
        assert c.get("/api/approvals/apr_nope/verification").status_code == 404
        assert c.post(f"/api/approvals/{a['id']}/merge", json={"pr": 1}).status_code == 400  # not approved
        assert c.post(f"/api/approvals/{a['id']}/preflight").json()["preflight"]["steps"] == []
        assert approvals.get(a["id"])["payload"]["preflight"]["steps"] == []
    finally:
        rw("MATCH (a:Approval {id: $id}) DELETE a", {"id": a["id"]}, approvals.agents_graph())
