"""Full ingest of the demo org into FalkorDB.

    python -m warden.ingest                # ingest at DEMO_REF into org_<tenant>
    python -m warden.ingest --snapshot     # ...then GRAPH.COPY to org_<tenant>_golden
    python -m warden.ingest --fresh        # drop the org graph first
    python -m warden.ingest --ref <sha|branch> --fetch   # re-sync from a newer commit (closed loop)
"""
import argparse
import json

from warden import config
from warden.ingest.pipeline import run


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
