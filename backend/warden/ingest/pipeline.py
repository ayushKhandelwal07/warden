"""Ingest pipeline: repo checkout at a ref -> services, dependencies, advisories, history -> FalkorDB graph.

Works on any repository: services come from Kubernetes manifests, a compose file or the code folders (see discover.py),
and the org data around them is curated for microservices-demo and inferred for anything else (see orgdata.py)."""
import time

from warden import config
from warden.graph.client import copy_graph, delete_graph, ro
from warden.graph.schema import ensure_schema
from warden.ingest import deps, discover, history, intel, load, orgdata, osv, repo
from warden.ingest.common import now_ms


class NothingToRead(ValueError):
    """The repo has no services Warden can read."""


def repo_name() -> str:
    return config.clone_url().rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]


def run(ref: str, fresh: bool = False, snapshot: bool = False, fetch: bool = False, use_nvd: bool = True, quiet: bool = False,
        progress=None) -> dict:
    g = config.org_graph_name()
    t0 = time.perf_counter()
    print_ = (lambda *a, **k: None) if quiet else print
    step = progress or (lambda msg: None)

    step("Fetching the repository")
    sha = repo.ensure_repo(ref, fetch=fetch)
    step("Finding services")
    m = discover.discover(config.repo_dir(), repo_name())
    if not m["services"]:
        raise NothingToRead("No services found. Warden reads Kubernetes manifests, a docker-compose file, or folders with a "
                            "dependency file (package.json, go.mod, requirements.txt, pom.xml, Cargo.lock and similar).")
    if fresh:
        delete_graph(g)
    ensure_schema(g)
    run_id = now_ms()
    print_(f"ingest run {run_id} at {ref} ({sha[:10]}) into {g}")
    org = orgdata.for_repo(m["services"], config.repo_dir())

    load.load_topology(m, org["descriptions"], run_id, sha, g)
    print_(f"  services={len(m['services'])} calls={len(m['calls'])} ingresses={len(m['ingresses'])} from {m['source']}")

    step(f"Reading the dependencies of {len(m['services'])} services")
    d = deps.parse_dependencies(m["services"])
    load.load_dependencies(d, run_id, sha, g)
    print_(f"  packages={len(d['packages'])} depends_on={len(d['depends'])} requires={len(d['requires'])}")

    step(f"Checking {len(d['packages'])} packages against OSV, CISA KEV and EPSS")
    o = osv.fetch_vulnerabilities(d["packages"])
    stats = intel.enrich(o["vulns"], use_nvd=use_nvd)
    load.load_vulnerabilities(o, run_id, g)
    print_(f"  vulns={len(o['vulns'])} affected_by={len(o['affected'])} intel={stats}")

    load.load_curated(org["teams"], org["assets"], org["policies"], run_id, g)
    if org["kind"] == "inferred":
        load.load_inferred_assets(orgdata.infer_assets(d), run_id, g)
    load.load_incidents(org["incidents"], run_id, g)

    step("Reading the commit history")
    h = history.parse_history(m["services"], ref="HEAD")
    load.load_history(h, g)
    load.derive_expertise(g)
    print_(f"  commits={len(h['commits'])} prs={len(h['prs'])} people={len(h['people'])} files={len(h['files'])} org={org['kind']}")

    removed = load.prune_stale(run_id, g)
    if any(removed.values()):
        print_(f"  pruned stale edges: { {k: v for k, v in removed.items() if v} }")

    kev = intel.kev_meta()
    load.record_run(run_id, ref, sha, kev, g, source=m["source"], org=org["kind"])
    try:
        from warden import contradictions

        c = contradictions.scan(g)
        print_(f"  contradictions: {c['open']} open")
    except Exception as e:  # a failed scan must never fail the ingest
        print_(f"  contradiction scan skipped: {type(e).__name__}")

    counts, _ = ro("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY n DESC", graph_name=g)
    if snapshot:
        copy_graph(g, config.golden_graph_name())
        print_(f"  snapshot -> {config.golden_graph_name()}")
    print_(f"done in {time.perf_counter() - t0:.1f}s")
    return {"run": run_id, "sha": sha, "counts": counts, "source": m["source"], "org": org["kind"],
            "services": len(m["services"]), "packages": len(d["packages"]), "vulns": len(o["vulns"])}
