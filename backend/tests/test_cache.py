"""Tool-result cache: hits on repeat, invalidated by any write to the graph. Skipped if FalkorDB is down."""
import pytest

from warden.graph.client import db, rw
from warden.tools import run_tool

try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False

pytestmark = pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")


def test_repeat_call_is_a_cache_hit_with_the_same_answer():
    a = run_tool("blast_radius", {"service": "cartservice", "depth": 2})
    b = run_tool("blast_radius", {"service": "cartservice", "depth": 2})
    assert b.get("cached") is True and b["summary"] == a["summary"] and b["rows"] == a["rows"]
    assert run_tool("blast_radius", {"service": "cartservice", "depth": 2}, use_cache=False).get("cached") is None


def test_a_write_to_the_graph_invalidates_it():
    run_tool("blast_radius", {"service": "cartservice", "depth": 1})
    rw("MATCH (s:Service {name: 'cartservice'}) SET s.cache_probe = timestamp()")
    assert run_tool("blast_radius", {"service": "cartservice", "depth": 1}).get("cached") is None
    rw("MATCH (s:Service {name: 'cartservice'}) REMOVE s.cache_probe")
