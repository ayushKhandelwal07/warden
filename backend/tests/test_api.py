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
