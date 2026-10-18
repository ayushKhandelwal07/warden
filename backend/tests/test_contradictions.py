"""Contradiction detection: each kind on a fixture, the gate abstaining, and the stored lifecycle in the live graph."""
import pytest

from warden import contradictions as c
from warden.graph.client import db, ro, rw
from warden.planner import _gate


def test_toolchain_mismatch_and_older_builder():
    gm = c.go_versions("module x\n\ngo 1.22\ntoolchain go1.22.5\n")
    assert gm == {"go": "1.22", "toolchain": "1.22.5"}
    assert c.check_toolchain("svc", gm, "1.22.5", "src/svc/go.mod") == []
    mismatch = c.check_toolchain("svc", gm, "1.21.0", "src/svc/go.mod")
    assert {m["subject"] for m in mismatch} == {"svc:toolchain", "svc:older-builder"} and mismatch[0]["sources"]
    assert c.check_toolchain("svc", {"go": "1.19", "toolchain": None}, "1.20.4", "go.mod") == []  # a newer builder than the directive is normal


def test_npm_range_check_never_guesses():
    assert c.satisfies("^1.1.0", "1.1.0") and c.satisfies("^1.1.0", "1.9.2") and not c.satisfies("^1.1.0", "2.0.0")
    assert c.satisfies("~1.2.3", "1.2.9") and not c.satisfies("~1.2.3", "1.3.0")
    assert c.satisfies("1.2.3", "1.2.3") and not c.satisfies("1.2.3", "1.2.4")
    assert c.satisfies("^0.2.3", "0.2.9") and not c.satisfies("^0.2.3", "0.3.0")
    assert c.satisfies(">=1 <3", "2.0.0") is None  # a range form we do not parse is not reported
    out = c.check_npm("pay", {"uuid": "^9.0.0", "lodash": "~4.17.0"}, {"uuid": "10.0.0", "lodash": "4.17.21"}, "package.json")
    assert [o["package"] for o in out] == ["uuid"]


def test_range_exposure_and_decision_checks():
    assert [o["vuln"] for o in c.check_range([{"vuln": "V1", "package": "p", "version": "2.0.0", "fixed": "1.5.0"}, {"vuln": "V2", "package": "p", "version": "1.0.0", "fixed": "1.5.0"}, {"vuln": "V3", "package": "p", "version": "1.0.0", "fixed": None}])] == ["V1"]
    ex = c.check_exposure([{"service": "a", "tier": "internal", "exposed": True}, {"service": "b", "tier": "public", "exposed": False}, {"service": "c", "tier": "public", "exposed": True}])
    assert [e["service"] for e in ex] == ["a", "b"]
    d = [{"id": "dec_1", "text": "Upgrade x", "status": "verified", "targets": [("V1", "a"), ("V2", "a")]}, {"id": "dec_2", "text": "y", "status": "approved", "targets": [("V1", "a")]}]
    assert [x["subject"] for x in c.check_decisions(d, {("V1", "a")})] == ["dec_1"]


def test_open_contradiction_makes_the_gate_abstain():
    side = {"findings": 3, "kev_findings": 0, "risk": 10.0, "keys": set(), "by_key": {}}
    ok = _gate({**side, "risk": 20.0}, side, [], None, [], None)
    assert ok["passed"]
    blocked = _gate({**side, "risk": 20.0}, side, [], None, [], [{"detail": "svc: go.mod says toolchain go1.22.5 but the Dockerfile builds with Go 1.21.0."}])
    failed = [x for x in blocked["checks"] if not x["ok"]]
    assert not blocked["passed"] and failed[0]["check"].startswith("no open evidence contradiction") and "toolchain" in failed[0]["detail"]


try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False


@pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")
def test_scan_lifecycle_tool_and_plan_abstention():
    from warden import planner, proposals
    from warden.tools import run_tool

    base = planner.build_plan(5)
    top = base["items"][0]
    rw("""CREATE (x:Contradiction {id: 'ctr_test', kind: 'toolchain', subject: 'test', detail: 'test: Dockerfile and go.mod disagree', resolution: 'align', sources_json: '["a","b"]',
        status: 'open', service: $s, package: $p, detected_at: 1})""", {"s": top["services"][0], "p": top["package"]})
    try:
        r = run_tool("contradictions_for", {"service": top["services"][0]})
        assert not r["error"] and r["rows"][0]["detail"].startswith("test:") and "Do not rely" in r["summary"]
        plan = planner.build_plan(5)
        assert plan["contradictions"] and not plan["gate"]["passed"]
        a, why = proposals.file_fix_plan(plan, "test")
        assert a is None and "no open evidence contradiction" in why
        scan = c.scan()  # the fixture is not detected by any real check, so it resolves
        assert ro("MATCH (x:Contradiction {id: 'ctr_test'}) RETURN x.status AS s")[0][0]["s"] == "resolved" and scan["checked"]["range"] > 0
    finally:
        rw("MATCH (x:Contradiction) DETACH DELETE x")
    assert run_tool("contradictions_for", {})["rows"] == []
