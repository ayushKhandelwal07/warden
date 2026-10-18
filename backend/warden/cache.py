"""Result cache in FalkorDB's own Redis keyspace (no extra service). Keys carry the graph's write version,
which every write bumps, so a cached answer can never outlive a change to the graph it came from."""
import hashlib
import json

from warden import config

# Bump when the shape of a cached result changes (the graph version only tracks data, not code).
SCHEMA = 2
TTL = 600 # seconds; versioning does the invalidation, the TTL only bounds memory
PREFIX = "warden:cache"


def _redis():
    from warden.graph.client import db

    return db().connection


def version(graph: str) -> int:
    try:
        return int(_redis().get(f"{PREFIX}:ver:{graph}") or 0)
    except Exception:
        return -1  # cache unavailable: callers treat -1 as "don't cache"


def bump(graph: str):
    """Called after any write to `graph` (rw, copy, delete)."""
    try:
        _redis().incr(f"{PREFIX}:ver:{graph}")
    except Exception:
        pass


def _key(kind: str, graph: str, ver: int, payload) -> str:
    h = hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:20]
    return f"{PREFIX}:{kind}:{graph}:{SCHEMA}:{ver}:{h}"


def cached(kind: str, payload, compute, graph: str | None = None):
    """Returns (value, hit). `compute()` runs on a miss; its result is stored if it's JSON-serialisable."""
    g = graph or config.org_graph_name()
    ver = version(g)
    if ver < 0:
        return compute(), False
    key = _key(kind, g, ver, payload)
    try:
        raw = _redis().get(key)
        if raw:
            return json.loads(raw), True
    except Exception:
        return compute(), False
    value = compute()
    try:
        _redis().set(key, json.dumps(value, default=str), ex=TTL)
    except Exception:
        pass
    return value, False
