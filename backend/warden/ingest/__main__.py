"""Full ingest of the demo org into FalkorDB.

    python -m warden.ingest                # ingest at DEMO_REF into org_<tenant>
    python -m warden.ingest --snapshot     # ...then GRAPH.COPY to org_<tenant>_golden
    python -m warden.ingest --fresh        # drop the org graph first
    python -m warden.ingest --ref <sha|branch> --fetch   # re-sync from a newer commit (closed loop)
"""
import argparse
import json
import time

import yaml

from warden import config
from warden.graph.client import copy_graph, delete_graph, ro
from warden.graph.schema import ensure_schema
from warden.ingest import deps, history, intel, load, manifests, osv, repo
from warden.ingest.common import now_ms


def _yaml(name: str):
    return yaml.safe_load((config.ORG_DIR / name).read_text(encoding="utf-8"))


def run(ref: str, fresh: bool, snapshot: bool, fetch: bool, use_nvd: bool) -> dict:
    g = config.org_graph_name()
    t0 = time.perf_counter()
    if fresh:
        delete_graph(g)
    sha = repo.ensure_repo(ref, fetch=fetch)
    ensure_schema(g)
    run_id = now_ms()
    print(f"ingest run {run_id} at {ref} ({sha[:10]}) into {g}")

    m = manifests.parse_manifests()
    load.load_topology(m, _yaml("services.yaml"), run_id, sha, g)
    print(f"  services={len(m['services'])} calls={len(m['calls'])} ingresses={len(m['ingresses'])}")

    d = deps.parse_dependencies(m["services"])
    load.load_dependencies(d, run_id, sha, g)
    print(f"  packages={len(d['packages'])} depends_on={len(d['depends'])} requires={len(d['requires'])}")

    o = osv.fetch_vulnerabilities(d["packages"])
    stats = intel.enrich(o["vulns"], use_nvd=use_nvd)
    load.load_vulnerabilities(o, run_id, g)
    print(f"  vulns={len(o['vulns'])} affected_by={len(o['affected'])} intel={stats}")

    load.load_curated(_yaml("teams.yaml")["teams"], _yaml("sensitivity.yaml")["data_assets"], _yaml("policies.yaml")["policies"], run_id, g)

    h = history.parse_history(m["services"], ref="HEAD")
    load.load_history(h, g)
    load.derive_expertise(g)
    print(f"  commits={len(h['commits'])} prs={len(h['prs'])} people={len(h['people'])} files={len(h['files'])}")

    removed = load.prune_stale(run_id, g)
    if any(removed.values()):
        print(f"  pruned stale edges: { {k: v for k, v in removed.items() if v} }")

    counts, _ = ro("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY n DESC", graph_name=g)
    if snapshot:
        copy_graph(g, config.golden_graph_name())
        print(f"  snapshot -> {config.golden_graph_name()}")
    print(f"done in {time.perf_counter() - t0:.1f}s")
    return {"run": run_id, "sha": sha, "counts": counts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=config.DEMO_REF)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--no-nvd", action="store_true", help="skip the NVD CVSS fallback (slow on a cold cache)")
    a = ap.parse_args()
    res = run(a.ref, a.fresh, a.snapshot, a.fetch, not a.no_nvd)
    print(json.dumps(res["counts"]))


if __name__ == "__main__":
    main()
