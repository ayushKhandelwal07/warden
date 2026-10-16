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

client = TestClient(api.app)
live = pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")


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
