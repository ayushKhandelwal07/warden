"""FalkorDB access. Reads go through GRAPH.RO_QUERY; writes only through rw()."""
import time
from functools import lru_cache

from falkordb import FalkorDB

from warden import config


@lru_cache(maxsize=1)
def db() -> FalkorDB:
    return FalkorDB(
        host=config.FALKORDB_HOST,
        port=config.FALKORDB_PORT,
        username=config.FALKORDB_USERNAME,
        password=config.FALKORDB_PASSWORD,
        ssl=config.FALKORDB_SSL,
    )


def graph(name: str | None = None):
    return db().select_graph(name or config.org_graph_name())


def ro(cypher: str, params: dict | None = None, graph_name: str | None = None):
    """Read-only query. Returns (rows as list[dict], ms)."""
    t0 = time.perf_counter()
    res = graph(graph_name).ro_query(cypher, params or {})
    return _rows(res), round((time.perf_counter() - t0) * 1000, 2)


def rw(cypher: str, params: dict | None = None, graph_name: str | None = None):
    t0 = time.perf_counter()
    res = graph(graph_name).query(cypher, params or {})
    return _rows(res), round((time.perf_counter() - t0) * 1000, 2)


def _rows(res) -> list[dict]:
    cols = [c[1] if isinstance(c, (list, tuple)) else c for c in res.header]
    return [dict(zip(cols, r)) for r in res.result_set]


def batched(rows: list, size: int = 500):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def unwind(cypher: str, rows: list[dict], graph_name: str | None = None, size: int = 500) -> int:
    """Run `UNWIND $rows AS row <cypher>` in batches. Returns rows sent."""
    n = 0
    for chunk in batched(rows, size):
        rw("UNWIND $rows AS row " + cypher, {"rows": chunk}, graph_name)
        n += len(chunk)
    return n


def graph_exists(name: str) -> bool:
    return name in db().list_graphs()


def copy_graph(src: str, dst: str) -> None:
    if graph_exists(dst):
        db().select_graph(dst).delete()
    db().select_graph(src).copy(dst)


def delete_graph(name: str) -> None:
    if graph_exists(name):
        db().select_graph(name).delete()
