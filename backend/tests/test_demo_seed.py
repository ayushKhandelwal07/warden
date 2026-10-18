"""Demo history: created once, labelled, and consistent with the live graph."""
import pytest

from warden import demo_seed
from warden.actions import approvals
from warden.graph.client import db, ro, rw

try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False


@pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")
def test_seed_is_idempotent_labelled_and_changes_the_plan():
    from warden import contradictions

    for a in approvals.list_all():
        rw("MATCH (a:Approval {id: $i}) DELETE a", {"i": a["id"]}, approvals.agents_graph())
    rw("MATCH (d:Decision) WHERE d.source_type = 'warden' DETACH DELETE d")
    try:
        first = demo_seed.seed()
        assert set(first["created"]) == {"rejected", "pending", "verified"}
        assert demo_seed.seed()["created"] == []
        items = approvals.list_all()
        assert len(items) == 3 and all(a["payload"]["demo"] for a in items)
        by = {a["payload"]["demo_kind"]: a for a in items}
        assert by["pending"]["status"] == "pending" and by["pending"]["payload"]["gate"]["checks"]
        assert by["rejected"]["status"] == "rejected" and by["rejected"]["reason"]
        mem = by["pending"]["payload"]["memory"]
        assert any(n["package"] == "google.golang.org/grpc" and n["action"] == "excluded" for n in mem["notes"])
        assert ro("MATCH (d:Decision {status: 'verified'}) RETURN count(d) AS n")[0][0]["n"] == 1
        assert contradictions.detect()[0] == []  # the verified demo decision promises nothing, so it cannot contradict the live graph
    finally:
        for a in approvals.list_all():
            rw("MATCH (a:Approval {id: $i}) DELETE a", {"i": a["id"]}, approvals.agents_graph())
        rw("MATCH (d:Decision) WHERE d.source_type = 'warden' DETACH DELETE d")
