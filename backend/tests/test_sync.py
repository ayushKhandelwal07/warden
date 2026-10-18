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


def test_what_if_changes_move_paths_and_never_touch_live():
    from warden import counterfactual
    from warden.graph.client import db

    live = config.org_graph_name()
    before_graphs = set(db().list_graphs())
    exp = counterfactual.what_if([{"op": "expose", "service": "paymentservice"}])
    assert exp["paths"]["after"] > exp["paths"]["before"] and exp["risk"]["after"] > exp["risk"]["before"]
    assert any("paymentservice" in r[0] for r in exp["paths"]["new"]) or exp["new"]
    cut = counterfactual.what_if([{"op": "remove_call", "from": "checkoutservice", "to": "paymentservice"}])
    assert cut["paths"]["after"] < cut["paths"]["before"] and cut["sensitive"]["no_longer_reachable"] == [] or cut["paths"]["removed"]
    up = counterfactual.what_if([{"op": "upgrade", "package": "golang.org/x/net"}])
    assert up["risk"]["kev_after"] < up["risk"]["kev_before"] and up["fixed"]
    assert set(db().list_graphs()) == before_graphs and live in before_graphs
    for bad in ([{"op": "explode"}], [{"op": "expose", "service": "nope"}], []):
        with pytest.raises(ValueError):
            counterfactual.what_if(bad)


def test_what_if_finds_a_best_intervention():
    from warden import counterfactual

    r = counterfactual.what_if([{"op": "expose", "service": "paymentservice"}], find_best=True)
    iv = r["intervention"]
    assert iv["tried"] and iv["best"]["risk_recovered"] > 0 and iv["best"]["risk_after"] < r["risk"]["after"]
