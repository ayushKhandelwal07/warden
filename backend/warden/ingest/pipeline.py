"""Ingest pipeline: repo checkout at a ref -> parsed sources -> FalkorDB org graph."""
import time

import yaml

from warden import config
from warden.graph.client import copy_graph, delete_graph, ro
from warden.graph.schema import ensure_schema
from warden.ingest import deps, history, intel, load, manifests, osv, repo
from warden.ingest.common import now_ms


def _yaml(name: str):
    return yaml.safe_load((config.ORG_DIR / name).read_text(encoding="utf-8"))


def run(ref: str, fresh: bool = False, snapshot: bool = False, fetch: bool = False, use_nvd: bool = True, quiet: bool = False) -> dict:
    g = config.org_graph_name()
    t0 = time.perf_counter()
    print_ = (lambda *a, **k: None) if quiet else print
    if fresh:
        delete_graph(g)
    sha = repo.ensure_repo(ref, fetch=fetch)
    ensure_schema(g)
    run_id = now_ms()
    print_(f"ingest run {run_id} at {ref} ({sha[:10]}) into {g}")

    m = manifests.parse_manifests()
    load.load_topology(m, _yaml("services.yaml"), run_id, sha, g)
    print_(f"  services={len(m['services'])} calls={len(m['calls'])} ingresses={len(m['ingresses'])}")

    d = deps.parse_dependencies(m["services"])
    load.load_dependencies(d, run_id, sha, g)
    print_(f"  packages={len(d['packages'])} depends_on={len(d['depends'])} requires={len(d['requires'])}")

    o = osv.fetch_vulnerabilities(d["packages"])
    stats = intel.enrich(o["vulns"], use_nvd=use_nvd)
    load.load_vulnerabilities(o, run_id, g)
    print_(f"  vulns={len(o['vulns'])} affected_by={len(o['affected'])} intel={stats}")

    load.load_curated(_yaml("teams.yaml")["teams"], _yaml("sensitivity.yaml")["data_assets"], _yaml("policies.yaml")["policies"], run_id, g)
    load.load_incidents(_yaml("postmortems.yaml")["incidents"], run_id, g)

    h = history.parse_history(m["services"], ref="HEAD")
    load.load_history(h, g)
    load.derive_expertise(g)
    print_(f"  commits={len(h['commits'])} prs={len(h['prs'])} people={len(h['people'])} files={len(h['files'])}")

    removed = load.prune_stale(run_id, g)
    if any(removed.values()):
        print_(f"  pruned stale edges: { {k: v for k, v in removed.items() if v} }")

    kev = intel.kev_meta()
    load.record_run(run_id, ref, sha, kev, g)

    counts, _ = ro("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY n DESC", graph_name=g)
    if snapshot:
        copy_graph(g, config.golden_graph_name())
        print_(f"  snapshot -> {config.golden_graph_name()}")
    print_(f"done in {time.perf_counter() - t0:.1f}s")
    return {"run": run_id, "sha": sha, "counts": counts}
