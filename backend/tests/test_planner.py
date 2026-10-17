"""Planner, patches and the approval gate, against the live graph. Approval/decision writes are cleaned up."""
import pytest

from warden import config
from warden.actions import approvals, github, patches
from warden.graph.client import db, rw
from warden.planner import build_plan

try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False

pytestmark = pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")


@pytest.fixture(scope="module")
def plan():
    return build_plan(5)


def test_plan_covers_kev_first_and_is_measured(plan):
    first = plan["items"][0]
    assert first["package"] == "golang.org/x/net" and first["kev"] and "CVE-2023-44487" in first["vulns"]
    assert plan["before"]["kev_findings"] > 0 and plan["after"]["kev_findings"] == 0
    assert plan["after"]["risk"] < plan["before"]["risk"]
    assert len(plan["removed"]) == plan["before"]["findings"] - plan["after"]["findings"] + len(plan["added"])


def test_rehearsal_copy_is_always_deleted(plan):
    assert plan["rehearsal"]["deleted"] and plan["rehearsal"]["graph"] not in db().list_graphs()


def test_patches_edit_the_real_manifests(plan):
    by_path = {f["path"]: f for s in patches.build_patches(plan["items"]) for f in s["files"]}
    gomod = by_path["src/frontend/go.mod"]
    assert gomod["changed"] and "+\tgolang.org/x/net v0.60.0" in gomod["diff"].replace("    ", "\t")
    assert "FROM golang:1.26.9-alpine AS builder" in by_path["src/frontend/Dockerfile"]["content"].replace(" as ", " AS ")


def test_major_bump_detection():
    assert patches.major_bump("6.1.12", "7.5.21") and not patches.major_bump("7.2.3", "7.6.3")
    assert patches.major_bump("v0.10.0", "v0.60.0")


def test_github_refuses_upstream(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", "x")
    monkeypatch.setattr(config, "GITHUB_OWNER", "GoogleCloudPlatform")
    with pytest.raises(PermissionError):
        github.target()


def test_approval_gate_without_github_executes_nothing(plan, monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", None)
    a = approvals.create("fix_plan", "test plan", plan["summary"], {**{k: v for k, v in plan.items() if k != "queries"}, "patches": []})
    try:
        assert a["status"] == "pending"
        done = approvals.approve(a["id"])
        assert done["status"] == "approved_not_executed" and done["result"]["executed"] is False
        with pytest.raises(ValueError):
            approvals.approve(a["id"])  # can't approve twice
    finally:
        rw("MATCH (a:Approval {id: $id}) DELETE a", {"id": a["id"]}, approvals.agents_graph())
        rw("MATCH (d:Decision {approval_id: $id}) DETACH DELETE d", {"id": a["id"]})
