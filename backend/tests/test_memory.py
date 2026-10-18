"""Decision memory and the temporal ledger: pure logic first, then a live rejection that really changes the next plan."""
import pytest

from warden import memory, timeline
from warden.graph.client import db, ro, rw

DAY = memory.DAY_MS
NOW = 1_800_000_000_000


def _d(status, days_ago=1, sha="aaa", frm="1.0.0"):
    return {"id": "dec_x", "status": status, "at": NOW - days_ago * DAY, "sha": sha, "reason": "broke checkout", "items": [{"package": "libx", "from": frm, "to": "2.0.0", "services": ["frontend"]}]}


VERSIONS = {"libx": {"frontend": {"1.0.0"}}}


def test_rejection_applies_while_the_package_is_unchanged_then_expires_or_is_superseded():
    assert memory.applies_now(_d("rejected"), VERSIONS, "aaa", NOW)["state"] == "active"
    assert memory.applies_now(_d("rejected", days_ago=120), VERSIONS, "aaa", NOW)["state"] == "expired"
    assert memory.applies_now(_d("rejected"), {"libx": {"frontend": {"1.5.0"}}}, "aaa", NOW)["state"] == "superseded"


def test_approval_is_fresh_only_for_the_same_versions_and_commit():
    assert memory.applies_now(_d("approved"), VERSIONS, "aaa", NOW)["state"] == "fresh"
    assert memory.applies_now(_d("approved"), VERSIONS, "bbb", NOW)["state"] == "stale"
    assert memory.applies_now(_d("approved"), {"libx": {"frontend": {"2.0.0"}}}, "aaa", NOW)["state"] == "done_or_changed"
    assert memory.applies_now({**_d("approved"), "items": []}, VERSIONS, "aaa", NOW)["applies"] is False


def test_timeline_from_diff_and_merge_order():
    diff = {"fixed": [{"vuln": "V1", "service": "a", "package": "p@1", "kev": True}], "new": [{"vuln": "V2", "service": "b", "package": "q@1", "hops": 1}],
            "exposure": {"added": ["b via b-external"], "removed": []}, "dependencies": {"moves": [{"change": "p 1 → 2", "services": ["a"]}]}, "calls": {"added": [], "removed": ["a → b"]}}
    ev = timeline.from_diff(diff, "v0.9.0", "abc", at=10)
    assert {e["kind"] for e in ev} == {"exposure_closed", "exposure_opened", "service_exposed", "dependency_changed", "call_removed"}
    merged = timeline.merge_events(ev, [{"id": "d1", "status": "approved", "text": "Upgrade p", "reason": None, "at": 20}], {"vuln": "V1", "added": 5, "name": "x"}, None, {"d1": "stale because"})
    assert [e["at"] for e in merged][:3] == [20, 20, 10] and merged[-1]["kind"] == "kev_listed"
    assert timeline.kev_added_ms("2023-10-10") and timeline.kev_added_ms("nope") is None


try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False
live = pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")


@live
def test_a_rejection_changes_the_next_plan_and_is_cited():
    from warden import planner
    from warden.actions import approvals

    base = planner.build_plan(5)
    top = base["items"][0]
    fake = {"id": "apr_memtest", "kind": "fix_plan", "title": "Upgrade (memory test)", "payload": {"items": [top], "removed": []}}
    approvals.record_decision(fake, "rejected", reason="broke checkout in staging", links=[], by="Dev Tester")
    try:
        again = planner.build_plan(5)
        mem = again["memory"]
        assert mem["changed"] and top["package"] in mem["changed"]["from"] and top["package"] not in mem["changed"]["to"]
        note = next(n for n in mem["notes"] if n["package"] == top["package"])
        assert note["action"] == "excluded" and note["reason"] == "broke checkout in staging" and note["by"] == "Dev Tester"
        assert top["package"] not in {i["package"] for i in again["items"]}
        # the decisions tool reports whether it still applies
        from warden.tools import run_tool

        r = run_tool("decisions_about", {"service": top["services"][0]})
        mine = [x for x in r["rows"] if x["status"] == "rejected" and "memory test" in x["decision"]]
        assert mine and mine[0]["applies_now"] is True
    finally:
        rw("MATCH (d:Decision {approval_id: 'apr_memtest'}) DETACH DELETE d")
    assert planner.build_plan(5)["memory"]["changed"] is None


@live
def test_exposure_timeline_reports_kev_and_state(monkeypatch):
    from warden.tools import run_tool

    r = run_tool("exposure_timeline", {"vuln": "CVE-2023-44487"})
    assert not r["error"] and "active" in r["summary"] and any(x["kind"] == "kev_listed" for x in r["rows"])
    ev = timeline.from_diff({"fixed": [{"vuln": "CVE-TEST-1", "service": "frontend", "package": "p@1", "kev": False}], "new": [], "exposure": {}, "dependencies": {}, "calls": {}}, "v1", "sha1")
    try:
        timeline.record({"fixed": [{"vuln": "CVE-TEST-1", "service": "frontend", "package": "p@1", "kev": False}]}, "v1", "sha1")
        rows = ro("MATCH (e:TimelineEvent {vuln: 'CVE-TEST-1'}) RETURN e.kind AS k")[0]
        assert [x["k"] for x in rows] == ["exposure_closed"] and ev
    finally:
        rw("MATCH (e:TimelineEvent {vuln: 'CVE-TEST-1'}) DELETE e")
