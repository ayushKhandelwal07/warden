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


def _nums(findings):
    return {"risk": sum(f["risk"] for f in findings), "kev_findings": sum(1 for f in findings if f["kev"]),
            "keys": {(f["vuln"], f["service"]) for f in findings}, "by_key": {(f["vuln"], f["service"]): f for f in findings}}


def _f(vuln, service, risk=10.0, kev=False, severity="HIGH", data=(), tier="exposed", package="pkg@1"):
    return {"vuln": vuln, "service": service, "risk": risk, "kev": kev, "severity": severity, "data": list(data), "tier": tier, "package": package}


def _gate_for(before_f, after_f, items=()):
    from warden import planner, regression

    assets = {"CardData": {"sensitivity": "PCI", "weight": 5}}
    b, a = _nums(before_f), _nums(after_f)
    reg = regression.classify(regression.invariants(before_f, assets), regression.invariants(after_f, assets))
    added = sorted(a["keys"] - b["keys"])
    return planner._gate(b, a, added, reg, list(items)), reg


def test_regression_compares_semantic_identity_not_package_shape():
    # the same (advisory, service) on a different package version is still the same exposure: remaining, not removed
    before = [_f("CVE-A", "frontend", kev=True, package="x@1")]
    after = [_f("CVE-A", "frontend", kev=True, package="x@2")]
    _, reg = _gate_for(before, after)
    assert reg["kev"]["remaining"][0]["package_before"] == "x@1" and reg["kev"]["remaining"][0]["package_after"] == "x@2"
    assert not reg["kev"]["removed"] and not reg["kev"]["new"]


def test_gate_passes_a_clean_fix_and_reports_what_is_gone():
    gate, reg = _gate_for([_f("CVE-A", "frontend", 40, kev=True), _f("CVE-B", "frontend", 5)], [_f("CVE-B", "frontend", 5)])
    assert gate["passed"] and len(reg["kev"]["removed"]) == 1
    assert all(c["level"] in ("block", "warn", "info") for c in gate["checks"])


def test_gate_blocks_a_fix_that_introduces_a_kev_exposure():
    gate, reg = _gate_for([_f("CVE-A", "frontend", 40, kev=True)], [_f("CVE-NEW", "frontend", 30, kev=True, severity="CRITICAL")])
    failed = [c["check"] for c in gate["checks"] if not c["ok"] and c["level"] == "block"]
    assert not gate["passed"] and "no new critical or KEV exposure" in failed
    assert [r["vuln"] for r in reg["kev"]["new"]] == ["CVE-NEW"]


def test_gate_blocks_a_serious_new_exposure_of_card_data_but_only_warns_for_a_minor_one():
    # paymentservice already had a low exposure, so only the *new* advisory is what the gate judges
    old = _f("CVE-OLD", "paymentservice", 2, severity="LOW", data=["CardData"])
    base = [_f("CVE-A", "frontend", 40, kev=True), old]
    serious, _ = _gate_for(base, [old, _f("CVE-H", "paymentservice", 8, severity="HIGH", data=["CardData"])])
    assert not serious["passed"] and any("PCI/PII" in c["check"] and not c["ok"] and c["level"] == "block" for c in serious["checks"])
    minor, _ = _gate_for(base, [old, _f("CVE-M", "paymentservice", 1, severity="MEDIUM", data=["CardData"])])
    assert minor["passed"] and any(c["level"] == "warn" and not c["ok"] and "lower-severity" in c["check"] for c in minor["checks"])


def test_gate_blocks_a_service_that_was_clean_and_is_now_exposed():
    gate, _ = _gate_for([_f("CVE-A", "frontend", 40)], [_f("CVE-A", "frontend", 30), _f("CVE-Z", "cartservice", 2, severity="LOW")])
    assert not gate["passed"] and any(c["check"].startswith("no service newly exposed") and not c["ok"] for c in gate["checks"])


def test_real_plan_records_regression_and_before_after_proof(plan):
    reg = plan["regression"]
    assert len(reg["kev"]["removed"]) == plan["before"]["kev_findings"] and not reg["kev"]["remaining"] and not reg["kev"]["new"]
    assert reg["sensitive"]["before"] >= reg["sensitive"]["after"] and reg["data"]["before"] == reg["data"]["after"]
    proof = plan["proof"]
    assert proof["removed"] and proof["vuln"] == "CVE-2023-44487" and proof["service"] == "frontend"
    assert {"Internet", "Ingress", "Service", "Package", "Vulnerability"} <= {n["label"] for n in proof["before"]["nodes"]}
    after_labels = {n["label"] for n in proof["after"]["nodes"]}
    assert "Package" in after_labels and "Vulnerability" not in after_labels  # same route, upgraded package, advisory gone
    assert plan["gate"]["passed"] and {c["level"] for c in plan["gate"]["checks"]} == {"block", "warn", "info"}


def test_optimizer_rows_are_rehearsed_and_constraints_hold():
    from warden import optimizer

    out = optimizer.compare({"max_changes": 4, "no_major": True})
    real = [r for r in out["rows"] if not r.get("empty") and not r.get("same_as")]
    assert real and all(r["majors"] == 0 and r["changes"] <= 4 for r in real)
    # The KEV fix (golang.org/x/net 0.x -> 0.60) is a major bump, so forbidding majors honestly leaves KEV open and the gate says so.
    assert all(r["residual_kev"] > 0 and not r["gate"] for r in real) and out["recommended"] is None
    free = optimizer.compare({})
    rows = [r for r in free["rows"] if not r.get("empty") and not r.get("same_as")]
    assert free["recommended"] in {r["id"] for r in rows if r["gate"] and r["residual_kev"] == 0}
    assert not any(optimizer._dominates(o, r) for r in rows if r["pareto"] for o in rows if o is not r)
    kev_only = next(r for r in free["rows"] if r["id"] == "kev_only")
    assert kev_only["residual_kev"] == 0 and kev_only["changes"] <= 2


def test_frozen_service_blocks_its_packages():
    from warden import optimizer
    from warden.tools.base import Trace
    from warden.tools.security import scored_paths

    paths = scored_paths(Trace())
    chosen = optimizer.select("max_risk", {"frozen_services": ["frontend"]}, paths)
    frozen_pkgs = {p["package_key"] for p in paths if p["service"] == "frontend"}
    assert all(c["package_key"] not in frozen_pkgs for c in chosen)
