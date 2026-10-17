"""Closed-loop pieces that don't mutate the live graph: diffs and what-if rehearsals."""
import pytest

from warden import config, sync
from warden.graph.client import db

try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False

pytestmark = pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")


def test_diff_of_a_graph_with_itself_is_empty():
    d = sync.diff_graphs(config.org_graph_name(), config.org_graph_name())
    assert d["fixed"] == [] and d["new"] == [] and d["worse"] == []
    assert d["dependencies"]["changed"] == 0 and d["before"] == d["after"]


def test_what_if_exposing_payment_raises_risk_and_leaves_no_copy():
    r = sync.what_if_expose("paymentservice")
    assert r["after"]["risk"] > r["before"]["risk"]
    assert r["worse"] and all(w["hops"] == 0 for w in r["worse"] if w["service"] == "paymentservice")
    assert r["exposure"]["added"] == ["paymentservice via paymentservice-external"]
    assert r["graph"] not in db().list_graphs()


def test_what_if_unknown_service_is_an_error():
    with pytest.raises(ValueError):
        sync.what_if_expose("billingservice")


def test_release_refs_start_at_the_demo_ref():
    refs = sync.available_refs()
    assert refs[0] == config.DEMO_REF and "v0.8.1" in refs
