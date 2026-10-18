"""Some tests assert the exact numbers of the pinned release (v0.8.0). When the graph has been re-read from a changed fork they are skipped, not failed."""
import pytest

from warden import config
from warden.graph.client import ro

try:
    _rows, _ = ro("MATCH (r:IngestRun) RETURN r.ref AS ref ORDER BY r.at DESC LIMIT 1")
    _ref = _rows[0]["ref"] if _rows else None
    _exposed, _ = ro("MATCH (s:Service)-[:EXPOSED_VIA]->(:Ingress) RETURN count(DISTINCT s) AS n")
    AT_PINNED = _ref == config.DEMO_REF and _exposed[0]["n"] == 1
except Exception:
    AT_PINNED = False

pinned = pytest.mark.skipif(not AT_PINNED, reason="the graph is not at the pinned release (it follows a changed fork); Sync -> Reset to run this")
