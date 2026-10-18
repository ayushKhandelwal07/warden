"""Every agent tool against the live org graph (run `python -m warden.ingest` first)."""
from pathlib import Path

import pytest

from warden.graph.client import db
from warden.tools import REGISTRY, run_tool

try:
    db().list_graphs()
    LIVE = True
except Exception:
    LIVE = False

pytestmark = pytest.mark.skipif(not LIVE, reason="FalkorDB not reachable")


def ok(name, **args):
    r = run_tool(name, args)
    assert r["error"] is None, r["error"]
    assert r["queries"], "every tool must show the queries it ran"
    return r


def labels(r):
    return {n["label"] for n in (r["evidence"] or {"nodes": []})["nodes"]}


def test_reachable_findings_puts_the_kev_hero_first_with_its_path():
    r = ok("reachable_findings", limit=5)
    top = r["rows"][0]
    assert (top["vuln"], top["service"], top["kev"], top["hops"]) == ("CVE-2023-44487", "frontend", True, 0)
    assert top["driver"] == "exploit"
    assert {"Internet", "Ingress", "Service", "Package", "Vulnerability", "Catalog"} <= labels(r)
    assert [x["risk"] for x in r["rows"]] == sorted((x["risk"] for x in r["rows"]), reverse=True)


def test_unreachable_service_abstains_instead_of_saying_safe():
    r = ok("reachable_findings", service="loadgenerator")
    assert r["rows"] == [] and r["summary"].startswith("No path in the graph")


def test_exploit_intel_reports_kev_and_exposure():
    r = ok("exploit_intel", vuln="cve-2023-44487")
    assert "On CISA KEV since 2023-10-10" in r["summary"]
    assert {"service": "frontend", "hops_from_internet": 0}.items() <= r["rows"][0].items()


def test_fix_path_direct_go_and_transitive_npm():
    go = ok("fix_path", vuln="CVE-2023-44487", service="frontend")["rows"][0]
    assert go["file"] == "src/frontend/go.mod" and go["to"] == "0.17.0"
    npm = ok("fix_path", vuln="CVE-2026-4800", service="paymentservice")
    row = npm["rows"][0]
    assert not row["direct"] and '"overrides"' in row["change"] and row["via"].endswith("lodash")
    assert len(npm["evidence"]["nodes"]) >= 4  # the REQUIRES chain is drawn


def test_blast_radius_depth_reveals_the_hidden_public_dependent():
    shallow = ok("blast_radius", service="paymentservice", depth=1)
    deep = ok("blast_radius", service="paymentservice", depth=3)
    assert [x["service"] for x in shallow["rows"]] == ["checkoutservice"]
    public = [x["service"] for x in deep["rows"] if x["internet_facing"]]
    assert public == ["frontend"] and "Internet" in labels(deep)


def test_path_between_service_and_data():
    r = ok("path_between", source="frontend", target="CardData")
    assert r["rows"][0]["path"] == "frontend → checkoutservice → CardData"


def test_betweenness_is_exact_and_stable():
    a = ok("rank", algorithm="betweenness")["rows"][:3]
    b = ok("rank", algorithm="betweenness")["rows"][:3]
    assert a == b == [{"service": "frontend", "score": 10.0}, {"service": "checkoutservice", "score": 4.0}, {"service": "cartservice", "score": 3.0}]


def test_pagerank_ranks_packages():
    rows = ok("rank", algorithm="pagerank", limit=5)["rows"]
    assert len(rows) == 5 and rows[0]["pagerank"] >= rows[-1]["pagerank"]


def test_people_tools():
    assert ok("who_owns", service="checkout")["rows"][0]["team"] == "Payments"
    r = ok("who_knows", service="checkoutservice")
    assert r["rows"] and r["rows"][0]["commits"] > 0 and "Commit" in labels(r)


def test_pr_touched_services():
    r = ok("pr_touched_services", pr=1840)
    assert "paymentservice" in [x["service"] for x in r["rows"]]
    assert run_tool("pr_touched_services", {"pr": 99999})["error"].startswith("PR #99999 is not in the graph")


def test_policies_for_cites_the_kev_policy():
    rows = ok("policies_for", vuln="CVE-2023-44487", service="frontend")["rows"]
    applying = [x["policy"] for x in rows if x["applies"]]
    assert applying == ["POL-KEV-48H"]


def test_find_entity_prefers_services_and_resolves_aliases():
    assert ok("find_entity", text="checkout")["rows"][0]["name"] == "checkoutservice"
    assert ok("find_entity", text="GHSA-qppj-fm5r-hxr3")["rows"][0]["name"] == "CVE-2023-44487"


def test_unknown_entities_and_bad_args_are_explicit_errors():
    assert "is not in the graph" in run_tool("blast_radius", {"service": "nosuchservice"})["error"]
    assert "between 1 and 4" in run_tool("blast_radius", {"service": "frontend", "depth": 9})["error"]
    assert run_tool("nope")["error"] == "unknown tool 'nope'"


def test_tools_never_write():
    src = "".join(p.read_text(encoding="utf-8") for p in (Path(__file__).parent.parent / "warden" / "tools").glob("*.py"))
    assert "rw(" not in src and ".query(" not in src
    assert len(REGISTRY) >= 11


def test_every_reachable_finding_has_a_tier_and_only_signal_tiers_have_signals():
    from warden.tools.risk import tier_of

    rows = ok("reachable_findings", limit=50)["rows"]
    assert rows and all(r["tier"] in ("exposed", "exploit_signal") for r in rows)
    top = rows[0]
    assert top["tier"] == "exploit_signal" and top["kev"]
    assert tier_of(False, 0.05) == "exposed" and tier_of(False, 0.1) == "exploit_signal" and tier_of(True, 0.0) == "exploit_signal"
    assert "graph-reachable" in ok("reachable_findings", limit=3)["summary"]


def test_every_hop_of_the_hero_path_has_provenance_and_calls_are_marked_inferred():
    r = ok("reachable_findings", limit=1, paths=1)
    edges = r["evidence"]["edges"]
    assert edges and all(e["provenance"]["kind"] in ("sourced", "inferred", "curated") and e["provenance"]["source"] for e in edges)
    by = {e["type"]: e["provenance"] for e in edges}
    assert by["DEPENDS_ON"]["url"].startswith("https://github.com/") and "go.mod" in by["DEPENDS_ON"]["source"]
    assert by["AFFECTED_BY"]["url"].startswith("https://osv.dev/vulnerability/")
    assert by["LISTED_IN"]["source"].startswith("CISA KEV, added 2023-10-10")
    from warden.graph.evidence import provenance

    assert provenance("CALLS", {"via": "grpc", "env_var": "X_ADDR"})["kind"] == "inferred"
