"""First-boot helper: build the graph and its golden snapshot only if they don't exist yet.

    python -m warden.ingest.bootstrap

Used by the starter scripts and the Docker entrypoint, so a fresh FalkorDB (local or Cloud) gets the demo
graph without anyone running the full ingest by hand. Safe to run on every start.
"""
import os

from warden import config
from warden.graph.client import copy_graph, graph_exists, ro
from warden.ingest.pipeline import run


def main():
    org, golden = config.org_graph_name(), config.golden_graph_name()
    has_org = graph_exists(org) and ro("MATCH (s:Service) RETURN count(s) AS n")[0][0]["n"] > 0
    if has_org:
        print(f"{org} already has data; skipping ingest.")
    else:
        # NVD backfill is slow on a cold cache (~6 s per CVE); off by default for first boot in a container.
        use_nvd = os.getenv("WARDEN_NVD", "0").lower() in ("1", "true", "yes")
        print(f"{org} is empty: ingesting {config.DEMO_REF} (NVD backfill {'on' if use_nvd else 'off'})…")
        run(config.DEMO_REF, snapshot=True, use_nvd=use_nvd)
    if not graph_exists(golden):
        copy_graph(org, golden)
        print(f"golden snapshot -> {golden}")


if __name__ == "__main__":
    main()
