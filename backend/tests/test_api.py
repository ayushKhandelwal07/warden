"""API tests against the live org graph (run `python -m warden.ingest` first). Skipped if FalkorDB is down."""
import pytest
from fastapi.testclient import TestClient

from warden.api import app as api
from warden.graph import overview
from warden.graph.client import db

try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False

import uuid

from warden.db import init_db

init_db()
client = TestClient(api.app)
live = pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")
PASSWORD = "correct horse battery"


def _signup(c: TestClient, name: str = "Test User") -> dict:
    r = c.post("/api/auth/signup", json={"email": f"t-{uuid.uuid4().hex[:8]}@example.com", "name": name, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


ME = _signup(client)


def test_signed_out_requests_are_refused_but_health_is_public():
    anon = TestClient(api.app)
    assert anon.get("/api/overview").status_code == 401
    assert anon.get("/api/auth/me").json()["user"] is None
    assert anon.get("/api/health").status_code in (200, 503)


def test_signup_joins_the_demo_project_and_a_personal_team():
    assert ME["user"]["name"] == "Test User"
    assert [p["slug"] for p in ME["projects"]] == ["online-boutique"]
    assert ME["projects"][0]["graph"] == "org_demo"
    assert {o["role"] for o in ME["orgs"]} == {"owner", "member"}
    assert client.get("/api/auth/me").json()["user"]["id"] == ME["user"]["id"]


def test_login_logout_and_bad_password():
    c = TestClient(api.app)
    me = _signup(c)
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").json()["user"] is None
    bad = c.post("/api/auth/login", json={"email": me["user"]["email"], "password": "nope-nope"})
    assert bad.status_code == 400 and "Wrong" in bad.json()["error"]
    ok = c.post("/api/auth/login", json={"email": me["user"]["email"], "password": PASSWORD})
    assert ok.status_code == 200 and c.get("/api/auth/me").json()["user"]["email"] == me["user"]["email"]
    assert c.post("/api/auth/signup", json={"email": me["user"]["email"], "name": "x", "password": PASSWORD}).status_code == 400


def test_unknown_project_is_forbidden():
    assert client.get("/api/overview", headers={"X-Project": "someone-elses"}).status_code == 403


def test_invite_link_adds_a_member_to_the_team():
    owner_c = TestClient(api.app)
    owner = _signup(owner_c, "Owner")
    team = next(o for o in owner["orgs"] if o["personal"])
    inv = owner_c.post(f"/api/orgs/{team['id']}/invites", json={}).json()
    assert TestClient(api.app).get(f"/api/invites/{inv['token']}").json()["org_name"] == team["name"]
    guest_c = TestClient(api.app)
    _signup(guest_c, "Guest")
    joined = guest_c.post(f"/api/invites/{inv['token']}/accept").json()
    assert team["id"] in {o["id"] for o in joined["orgs"]}
    names = {m["name"] for m in owner_c.get(f"/api/orgs/{team['id']}/members").json()}
    assert names == {"Owner", "Guest"}
    # a member can't invite; the link can't be reused
    assert guest_c.post(f"/api/orgs/{team['id']}/invites", json={}).status_code == 403
    assert TestClient(api.app).get(f"/api/invites/{inv['token']}").status_code == 404


@live
def test_health_reports_graph_and_provenance():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["nodes"] > 1000 and body["edges"] > 1000
    assert body["ingest"]["sha"] and body["kev"]["version"]


@live
def test_overview_hero_is_the_kev_path_in_order():
    body = client.get("/api/overview").json()
    t = body["totals"]
    assert t["services"] == 12 and t["kev"] >= 1 and t["exposed_services"] == 1
    assert sum(s["n"] for s in t["by_severity"]) == t["vulnerabilities"]
    hero = body["hero"]
    assert hero["facts"]["vuln"] == "CVE-2023-44487" and hero["facts"]["hops"] == 0
    labels = [n["label"] for n in sorted(hero["evidence"]["nodes"], key=lambda n: n["order"])]
    assert labels == ["Internet", "Ingress", "Service", "Package", "Vulnerability", "Catalog"]
    ids = {n["id"] for n in hero["evidence"]["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in hero["evidence"]["edges"])


def test_health_returns_503_when_graph_unreachable(monkeypatch):
    def boom():
        raise ConnectionError("connection refused")

    monkeypatch.setattr(overview, "health", boom)
    r = client.get("/api/health")
    assert r.status_code == 503 and r.json()["status"] == "down"


def _fake_agent(monkeypatch):
    async def run_turn(question, history=None):
        yield {"type": "start", "model": "fake", "via": "direct", "tools": 0}
        yield {"type": "answer", "text": f"answer to {question} (history {len(history or [])})", "verdict": {"ok": True}, "steps": 0, "ms": 1}

    monkeypatch.setattr(api.agent, "run_turn", run_turn)


def _ask(c: TestClient, question: str, cid: str | None = None) -> list[dict]:
    import json as _json

    r = c.post("/api/ask", json={"question": question, "conversation_id": cid})
    return [_json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]


def test_ask_saves_the_chat_and_its_history(monkeypatch):
    _fake_agent(monkeypatch)
    evs = _ask(client, "What should we fix first?")
    assert evs[0]["type"] == "conversation" and evs[0]["title"] == "What should we fix first?"
    cid = evs[0]["id"]
    evs2 = _ask(client, "And then?", cid)
    assert evs2[0]["id"] == cid and evs2[-1]["text"].endswith("(history 2)")
    chat = client.get(f"/api/conversations/{cid}").json()
    assert [m["role"] for m in chat["messages"]] == ["user", "assistant", "user", "assistant"]
    assert chat["messages"][1]["data"]["events"][-1]["type"] == "answer"
    assert cid in {c["id"] for c in client.get("/api/conversations").json()}


def test_chats_are_private_until_shared(monkeypatch):
    _fake_agent(monkeypatch)
    cid = _ask(client, "private question")[0]["id"]
    other = TestClient(api.app)
    _signup(other, "Teammate")  # same demo project
    assert other.get(f"/api/conversations/{cid}").status_code == 404
    assert cid not in {c["id"] for c in other.get("/api/conversations").json()}
    # rename + share
    assert client.patch(f"/api/conversations/{cid}", json={"title": "Renamed", "shared": True}).json()["title"] == "Renamed"
    seen = other.get(f"/api/conversations/{cid}").json()
    assert seen["title"] == "Renamed" and seen["mine"] is False and seen["owner"] == "Test User"
    # shared is read-only for others: no rename, delete or new turns
    assert other.patch(f"/api/conversations/{cid}", json={"title": "x"}).status_code == 403
    assert other.delete(f"/api/conversations/{cid}").status_code == 403
    assert _ask(other, "hijack", cid)[0]["type"] == "error"
    assert client.delete(f"/api/conversations/{cid}").status_code == 200
    assert client.get(f"/api/conversations/{cid}").status_code == 404


@live
def test_impact_run_is_saved_and_reopenable():
    r = client.post("/api/impact", json={"pr": 1789, "source": "history"}).json()
    assert r["report"]["pr"] == 1789 and r["run_id"]
    runs = client.get("/api/conversations?kind=impact").json()
    assert runs[0]["id"] == r["run_id"] and runs[0]["title"].startswith("#1789")
    saved = client.get(f"/api/conversations/{r['run_id']}").json()
    assert saved["messages"][-1]["data"]["report"]["risk"]["label"] == r["report"]["risk"]["label"]
    assert r["run_id"] not in {c["id"] for c in client.get("/api/conversations?kind=ask").json()}


@live
def test_single_approval_and_missing_one():
    items = client.get("/api/approvals").json()
    if items:
        one = client.get(f"/api/approvals/{items[0]['id']}").json()
        assert one["id"] == items[0]["id"] and one["title"] == items[0]["title"]
    assert client.get("/api/approvals/apr_doesnotexist").status_code == 404


@live
def test_public_overview_works_signed_out():
    body = TestClient(api.app).get("/api/public/overview").json()
    assert body["totals"]["services"] == 12 and body["hero"]["facts"]["vuln"] == "CVE-2023-44487"


@live
def test_tool_runs_are_saved_unless_preview():
    before = len(client.get("/api/tool-runs").json())
    assert "run_id" not in client.post("/api/tools/blast_radius?save=false", json={"service": "paymentservice"}).json()
    assert len(client.get("/api/tool-runs").json()) == before
    r = client.post("/api/tools/blast_radius", json={"service": "paymentservice", "depth": 3}).json()
    runs = client.get("/api/tool-runs").json()
    assert runs[0]["id"] == r["run_id"] and runs[0]["tool"] == "blast_radius"
    assert client.get(f"/api/tool-runs/{r['run_id']}").json()["result"]["summary"] == r["summary"]
    other = TestClient(api.app)
    _signup(other)
    assert other.get(f"/api/tool-runs/{r['run_id']}").status_code == 404


@live
def test_new_project_gets_its_own_graph_and_isolation():
    from warden.graph.client import graph_exists

    owner_c = TestClient(api.app)
    owner = _signup(owner_c, "Proj Owner")
    team = next(o for o in owner["orgs"] if o["personal"])
    made = owner_c.post("/api/projects", json={"org_id": team["id"], "name": "Payments"}).json()
    p = made["project"]
    assert p["graph"].startswith("proj_") and graph_exists(p["graph"]) and graph_exists(p["graph"] + "_golden")
    hdr = {"X-Project": p["slug"]}
    assert owner_c.get("/api/health", headers=hdr).json()["graph"] == p["graph"]
    assert owner_c.get("/api/overview", headers=hdr).json()["totals"]["services"] == 12
    assert owner_c.get("/api/approvals", headers=hdr).json() == []  # its own agents graph
    # a stranger can't reach it; a member of the demo team can't create projects there
    assert client.get("/api/overview", headers=hdr).status_code == 403
    assert client.post("/api/projects", json={"org_id": "demo", "name": "x"}).status_code == 403
    assert owner_c.delete(f"/api/projects/{p['id']}").status_code == 200
    assert not graph_exists(p["graph"])


@live
def test_funnel_numbers_equal_their_own_cypher_and_are_consistent():
    from warden.graph.client import ro

    f = client.get("/api/metrics").json()
    for st in f["stages"] + f["instances"]:
        assert ro(st["cypher"])[0][0]["n"] == st["n"], st["key"]  # the shown number is what the shown query returns
        assert st["definition"] and st["unit"]
    by = {s["key"]: s["n"] for s in f["stages"] + f["instances"]}
    # overlapping filters over the same 256 advisories: each is a subset of the previous bound
    assert by["present"] >= by["reachable"] >= by["signal"] >= by["kev"] >= 1
    assert by["entry"] <= by["reachable"]
    # one KEV advisory in several services is several exposures
    assert by["kev_exposures"] >= by["kev"] and by["exposures"] >= by["reachable"]
    assert f["snapshot"]["ingest"]["sha"] and f["snapshot"]["kev_catalog"]["version"]
    assert client.get("/api/overview").json()["funnel"]["stages"][0]["n"] == by["present"]


@live
def test_path_validation_rechecks_each_hop_in_the_graph():
    hero = client.get("/api/overview").json()["hero"]["evidence"]
    ids = [e["id"] for e in hero["edges"]]
    ok_ = client.post("/api/evidence/validate", json={"edges": ids}).json()
    assert ok_["valid"] and ok_["checked"] == len(ids)
    bad = client.post("/api/evidence/validate", json={"edges": ids + ["e99999999"]}).json()
    assert not bad["valid"] and [h for h in bad["hops"] if not h["present"]][0]["edge"] == "e99999999"
    assert client.post("/api/evidence/validate", json={}).status_code == 400


@live
def test_unsafe_demo_plan_is_blocked_by_the_gate_and_never_filed():
    before = len(client.get("/api/approvals").json())
    plan = client.post("/api/plans/unsafe").json()
    assert plan["unsafe_demo"] and not plan["gate"]["passed"]
    failed = {c["check"] for c in plan["gate"]["checks"] if not c["ok"] and c["level"] == "block"}
    # Whether total risk also rises depends on live OSV data for the old pin; the KEV check is the invariant.
    assert "KEV exposures eliminated or reduced" in failed
    assert len(client.get("/api/approvals").json()) == before


def _f(vuln, service, cvss, risk, kev=False, severity="HIGH", hops=0, tier="exposed", data=()):
    return {"vuln": vuln, "service": service, "cvss": cvss, "risk": risk, "kev": kev, "severity": severity, "hops": hops, "tier": tier,
            "epss": 0.01, "package": "p@1", "data": list(data), "data_weight": 0, "factors": {"exposure": 0.5 ** hops}}


def test_baseline_ranks_the_same_universe_two_ways_and_is_deterministic():
    from warden.baseline import compare

    fs = [_f("A", "s1", 9.8, 2.0, hops=2), _f("B", "s2", 9.8, 1.0, hops=3), _f("C", "frontend", 6.9, 48.0, kev=True, tier="exploit_signal"),
          _f("D", "s3", 7.0, 3.0, hops=1)]
    c = compare(fs, n=2)
    assert c["universe"] == 4
    assert [r["vuln"] for r in c["baseline_top"]] == ["A", "B"]  # CVSS desc, ties by advisory id
    assert [r["vuln"] for r in c["graph_top"]] == ["C", "D"]  # risk desc
    assert c["overlap"] == 0 and [r["vuln"] for r in c["kev_aware"]["top"]] == ["C", "A"]
    assert c["kev_positions"][0]["baseline_rank"] == 4 and c["kev_positions"][0]["graph_rank"] == 1
    h = c["headline"]  # C (6.9) vs D (7.0): within 1 CVSS point, the graph ranks C 16x higher
    assert (h["scanner_pick"]["vuln"], h["graph_pick"]["vuln"]) == ("D", "C") and h["risk_ratio"] >= 2
    assert compare(fs, n=2) == c


@live
def test_baseline_endpoint_on_the_real_graph_is_internally_consistent():
    c = client.get("/api/baseline").json()
    f = client.get("/api/metrics").json()
    exposures = next(s["n"] for s in f["instances"] if s["key"] == "exposures")
    assert c["universe"] == exposures  # same universe as the funnel's exposure count
    cvss = [r["cvss"] for r in c["baseline_top"]]
    assert cvss == sorted(cvss, reverse=True)
    risk = [r["risk"] for r in c["graph_top"]]
    assert risk == sorted(risk, reverse=True)
    assert 0 <= c["overlap"] <= c["n"] and c["kev_positions"], "the KEV exposures are tracked in both rankings"
    assert all(1 <= r["baseline_rank"] <= c["universe"] and 1 <= r["graph_rank"] <= c["universe"] for r in c["kev_positions"])


@live
def test_services_list_and_whatif_endpoint():
    svcs = client.get("/api/services").json()
    assert {"paymentservice", "frontend"} <= {s["name"] for s in svcs} and [s["name"] for s in svcs if s["entry"]] == ["frontend"]
    r = client.post("/api/whatif", json={"changes": [{"op": "remove_call", "from": "checkoutservice", "to": "paymentservice"}]}).json()
    assert r["paths"]["after"] < r["paths"]["before"] and r["changes"][0]["label"].startswith("stop checkoutservice")
    assert client.post("/api/whatif", json={"changes": [{"op": "expose", "service": "nope"}]}).json()["error"]
    legacy = client.post("/api/whatif", json={"service": "paymentservice"}).json()
    assert legacy["service"] == "paymentservice" and legacy["deleted"] and "fixed" in legacy


def _fake_turn(monkeypatch, tool_args):
    async def run_turn(question, history=None):
        from warden.tools import run_tool as rt

        res = rt("choke_points", tool_args)
        yield {"type": "tool_call", "id": "c1", "tool": "choke_points", "args": tool_args, "via": "mcp"}
        yield {"type": "tool_result", "id": "c1", "result": res}
        yield {"type": "tool_call", "id": "c2", "tool": "propose_fix_plan", "args": {}, "via": "local"}
        yield {"type": "tool_result", "id": "c2", "result": {"tool": "propose_fix_plan", "rows": [], "summary": "s", "queries": []}}
        yield {"type": "answer", "text": "Secure checkoutservice first."}

    monkeypatch.setattr(api.agent, "run_turn", run_turn)


@live
def test_replay_reproduces_and_reports_a_change(monkeypatch):
    _fake_turn(monkeypatch, {"limit": 3})
    evs = _ask(client, "Which service first?")
    cid = evs[0]["id"]
    saved = client.get(f"/api/conversations/{cid}").json()["messages"][-1]["data"]
    assert saved["snapshot"]["graph"] and "graph_version" in saved["snapshot"]
    r = client.post(f"/api/replay/{cid}/1", json={}).json()
    assert r["reproduced"] and [c["status"] for c in r["calls"]] == ["same", "not_replayed"]
    assert client.post(f"/api/replay/{cid}/9", json={}).status_code == 404


def test_replay_events_reports_changed_rows_and_errors_without_touching_the_graph():
    from warden import replay

    ev = [{"type": "tool_call", "id": "1", "tool": "choke_points", "args": {}}, {"type": "tool_result", "id": "1", "result": {"rows": [{"service": "a"}, {"service": "b"}], "summary": "s", "queries": []}},
          {"type": "tool_call", "id": "2", "tool": "choke_points", "args": {}}, {"type": "tool_result", "id": "2", "result": {"rows": [{"service": "a"}], "queries": []}},
          {"type": "tool_call", "id": "3", "tool": "choke_points", "args": {}}, {"type": "tool_result", "id": "3", "result": {"rows": [], "queries": []}}]
    outs = iter([{"rows": [{"service": "a"}], "summary": "s2"}, {"rows": [{"service": "a"}]}, {"error": "gone", "rows": []}])
    calls = replay.replay_events(ev, None, lambda *a, **k: next(outs))
    assert [c["status"] for c in calls] == ["changed", "same", "error"]
    assert calls[0]["removed"] == [{"service": "b"}] and calls[0]["added"] == [] and calls[0]["summary_after"] == "s2"
