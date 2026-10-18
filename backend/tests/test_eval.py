"""The evaluation suite runs on throwaway graphs and its scorecard follows the scenarios' known answers."""
import pytest

from warden import eval as ev
from warden.graph.client import db

try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False

pytestmark = pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")


@pytest.fixture(scope="module")
def card():
    return ev.run()


def test_every_scenario_ran_and_matches_its_known_answer(card):
    assert all(s["status"] == "ran" for s in card["scenarios"]), [s for s in card["scenarios"] if s["status"] != "ran"]
    assert [s["id"] for s in card["scenarios"] if not s["warden"]["ok"]] == []


def test_scorecard_reports_the_baseline_and_pending_scenarios(card):
    m = card["metrics"]
    assert m["reachability"]["warden"]["precision"] == 100 and m["reachability"]["baseline"]["precision"] < 100
    assert m["gate"]["n"] == 3 and m["abstain"]["n"] == 1 and m["priority"]["n"] == 2 and m["choke"]["n"] == 1 and m["memory"]["n"] == 1
    assert m["latency_ms"]["p95"] is not None
    assert {p["id"] for p in card["pending"]} == {"contradiction"}


def test_eval_graphs_are_deleted(card):
    assert [g for g in db().list_graphs() if g.startswith("eval_")] == []
    assert ev.last()["at"] == card["at"]
