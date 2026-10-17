"""PR impact analysis on real PRs from the ingested history."""
import pytest

from warden.graph.client import db
from warden.impact import TITLE_PKG, analyze, render_comment
from warden.tools import run_tool

try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False

pytestmark = pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")


def test_title_package_extraction():
    assert TITLE_PKG.search("fix(deps): update module google.golang.org/grpc to v1.55.0").group(1) == "google.golang.org/grpc"
    assert TITLE_PKG.search("fix(deps): update opentelemetry-js monorepo to v0.39.1").group(1) == "opentelemetry-js"


def test_grpc_upgrade_is_high_risk_with_matching_incident_and_reviewers():
    r = analyze(1789)
    assert r["risk"]["label"] == "high"
    assert r["incidents"][0]["incident"] == "PM-003" and r["incidents"][0]["same_kind_of_change"]
    assert r["reviewers"] and all(x["commits"] > 0 for x in r["reviewers"])
    assert any(p["policy"] == "POL-PCI-REVIEW" for p in r["policies"])


def test_risk_labels_differ_by_graph_facts():
    assert analyze(1795)["risk"]["label"] == "medium"
    assert analyze(1834)["risk"]["label"] == "low"


def test_comment_never_mentions_people_with_at():
    body = render_comment(analyze(1789))
    assert "@" not in body.replace("@0.", "") and "synthetic" in body


def test_past_incidents_matches_change_kind():
    r = run_tool("past_incidents", {"services": ["paymentservice"], "package": "opentelemetry-js"})
    assert r["rows"][0]["incident"] == "PM-001" and r["rows"][0]["same_kind_of_change"]


def test_unknown_pr_is_an_explicit_error():
    from warden.tools.base import ToolError

    with pytest.raises(ToolError):
        analyze(99999)
