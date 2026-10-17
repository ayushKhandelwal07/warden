"""Indexes and unique constraints for the org graph. Safe to re-run."""
from warden.graph.client import graph

# (label, key property) for exact-match lookups; every MERGE in ingestion uses these keys.
RANGE_INDEXES = [
    ("Service", "name"),
    ("Ingress", "name"),
    ("DataAsset", "name"),
    ("Team", "slug"),
    ("Person", "key"),
    ("Package", "key"),
    ("Package", "name"),
    ("Vulnerability", "id"),
    ("Catalog", "name"),
    ("PullRequest", "number"),
    ("Commit", "sha"),
    ("File", "path"),
    ("Policy", "id"),
    ("Incident", "id"),
    ("Document", "id"),
    ("Finding", "id"),
    ("Decision", "id"),
    ("Thread", "id"),
]

UNIQUE = [
    ("Service", "name"),
    ("Package", "key"),
    ("Vulnerability", "id"),
    ("Commit", "sha"),
    ("File", "path"),
]

FULLTEXT = [
    ("Service", ["name", "description"]),
    ("Package", ["name"]),
    ("Vulnerability", ["id", "summary"]),
    ("Person", ["name", "login"]),
    ("PullRequest", ["title"]),
    ("Incident", ["title", "summary"]),
]


def ensure_schema(graph_name: str | None = None) -> list[str]:
    g = graph(graph_name)
    notes = []
    for label, prop in RANGE_INDEXES:
        notes.append(_try(lambda: g.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"), f"index {label}.{prop}"))
    for label, props in FULLTEXT:
        args = ", ".join(f"'{p}'" for p in [label, *props])
        notes.append(_try(lambda: g.query(f"CALL db.idx.fulltext.createNodeIndex({args})"), f"fulltext {label}"))
    for label, prop in UNIQUE:
        notes.append(_try(lambda: g.create_node_unique_constraint(label, prop), f"unique {label}.{prop}"))
    return notes


def _try(fn, what: str) -> str:
    try:
        fn()
        return f"created {what}"
    except Exception as e:  # already exists, etc.
        return f"skipped {what}: {str(e).splitlines()[0][:80]}"
