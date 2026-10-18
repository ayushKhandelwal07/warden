"""Evaluation scenarios. Each builds a tiny graph in the real schema (`eval_<id>`), runs the real tools, planner gate and
chooser against it, compares with a known answer, and deletes the graph.

The known answers are written by the authors from the scenario's construction, so the scorecard measures whether the
code behaves as designed on controlled topologies. It is not a benchmark on third-party data (see the limitations).

Severity-only baseline = a scanner that ranks every present advisory by CVSS, has no reachability, no remediation gate and
never abstains. It is asked the same questions of the same graph.
"""
import time

from warden import regression
from warden.graph.client import delete_graph, ro, rw
from warden.planner import _gate, _summary_numbers, choose
from warden.tools.base import Trace
from warden.tools.security import best_findings, scored_paths

_LAST: dict = {}

CARD = {"card_data": (5, "PCI")}


def build(g: str, spec: dict) -> None:
    """spec: services {name: [assets read]}, entry, calls [(a, b)], assets {name: (weight, sensitivity)},
    deps [(service, package, version, direct, [(vuln, severity, cvss, kev, epss, fixed)])]"""
    delete_graph(g)
    rw("CREATE (:Internet {name: 'internet'})-[:REACHES]->(:Ingress {name: 'ingress'})", graph_name=g)
    for name, (weight, sens) in spec.get("assets", {}).items():
        rw("CREATE (:DataAsset {name: $n, weight: $w, sensitivity: $s})", {"n": name, "w": weight, "s": sens}, g)
    for name, reads in spec["services"].items():
        rw("CREATE (:Service {name: $n})", {"n": name}, g)
        for a in reads:
            rw("MATCH (s:Service {name: $n}), (d:DataAsset {name: $a}) CREATE (s)-[:READS]->(d)", {"n": name, "a": a}, g)
    rw("MATCH (s:Service {name: $n}), (i:Ingress) CREATE (s)-[:EXPOSED_VIA]->(i)", {"n": spec["entry"]}, g)
    for a, b in spec.get("calls", []):
        rw("MATCH (a:Service {name: $a}), (b:Service {name: $b}) CREATE (a)-[:CALLS]->(b)", {"a": a, "b": b}, g)
    for svc, pkg, ver, direct, vulns in spec.get("deps", []):
        key = f"npm:{pkg}@{ver}"
        rw(
            "MATCH (s:Service {name: $s}) MERGE (p:Package {key: $k}) SET p.name = $n, p.version = $v, p.ecosystem = 'npm' "
            "CREATE (s)-[:DEPENDS_ON {direct: $d, manifest: 'eval/package-lock.json'}]->(p)",
            {"s": svc, "k": key, "n": pkg, "v": ver, "d": direct},
            g,
        )
        for vid, sev, cvss, kev, epss, fixed in vulns:
            rw(
                "MERGE (v:Vulnerability {id: $id}) SET v.severity = $sev, v.cvss = $cvss, v.kev = $kev, v.epss = $epss, v.summary = 'eval scenario'",
                {"id": vid, "sev": sev, "cvss": cvss, "kev": kev, "epss": epss},
                g,
            )
            if fixed is None:
                rw("MATCH (p:Package {key: $k}), (v:Vulnerability {id: $id}) CREATE (p)-[:AFFECTED_BY]->(v)", {"k": key, "id": vid}, g)
            else:
                rw("MATCH (p:Package {key: $k}), (v:Vulnerability {id: $id}) CREATE (p)-[:AFFECTED_BY {fixed: $f}]->(v)", {"k": key, "id": vid, "f": fixed}, g)


def _present_pairs(g: str) -> set[tuple]:
    rows, _ = ro("MATCH (s:Service)-[:DEPENDS_ON]->(:Package)-[:AFFECTED_BY]->(v:Vulnerability) RETURN DISTINCT v.id AS v, s.name AS s", {}, g)
    return {(r["v"], r["s"]) for r in rows}


def _counts(pred: set, truth: set) -> dict:
    return {"tp": len(pred & truth), "fp": len(pred - truth), "fn": len(truth - pred)}


def _cvss_top(g: str) -> str:
    rows, _ = ro("MATCH (s:Service)-[:DEPENDS_ON]->(:Package)-[:AFFECTED_BY]->(v:Vulnerability) RETURN v.id AS v, s.name AS s, v.cvss AS c", {}, g)
    best = sorted(rows, key=lambda r: (-(r["c"] or 0), r["v"], r["s"]))[0]
    return f"{best['v']} in {best['s']}"


def _base(services, entry="frontend", **kw):
    return {"services": services, "entry": entry, **kw}


def _V(vid, sev="HIGH", cvss=7.5, kev=False, epss=0.01, fixed="9.9.9"):
    return (vid, sev, cvss, kev, epss, fixed)


def _pairs_text(pairs) -> str:
    return ", ".join(f"{v} on {s}" for v, s in sorted(pairs)) or "nothing reachable"


def _gate_run(before_g: str, after_g: str):
    trace = Trace()
    bp, ap = scored_paths(trace, graph_name=before_g), scored_paths(trace, graph_name=after_g)
    assets = regression.sensitive_assets(trace, before_g)
    reg = regression.classify(regression.invariants(best_findings(bp), assets), regression.invariants(best_findings(ap), assets))
    b, a = _summary_numbers(bp), _summary_numbers(ap)
    items = [{"package": "libnet", "from": "1.0.0", "to": "1.1.0"}]
    gate = _gate(b, a, sorted(a["keys"] - b["keys"]), reg, items)
    return gate, trace, a


def _gate_text(gate) -> str:
    return "gate passed" if gate["passed"] else "gate blocked: " + "; ".join(c["check"] for c in gate["checks"] if not c["ok"] and c["level"] == "block")


# ── scenarios ───────────────────────────────────────────────────────────────────────────────────────────────────

def s_reachable_direct(g):
    build(g, _base({"frontend": [], "catalog": []}, calls=[("frontend", "catalog")], deps=[("frontend", "libweb", "1.0.0", True, [_V("EVAL-1")])]))
    trace = Trace()
    found = {(f["vuln"], f["service"]) for f in best_findings(scored_paths(trace, graph_name=g))}
    return {"truth": {("EVAL-1", "frontend")}, "w": found, "b": _present_pairs(g), "trace": trace,
            "expected": "EVAL-1 reachable on frontend (0 hops)", "answer": _pairs_text(found)}


def s_unreachable(g):
    build(g, _base({"frontend": [], "reports": []}, deps=[("reports", "libpdf", "2.0.0", True, [_V("EVAL-2", "CRITICAL", 9.8)])]))
    trace = Trace()
    found = {(f["vuln"], f["service"]) for f in best_findings(scored_paths(trace, graph_name=g))}
    return {"truth": set(), "w": found, "b": _present_pairs(g), "trace": trace,
            "expected": "nothing reachable: the CRITICAL advisory is in a service nothing calls", "answer": _pairs_text(found)}


def s_transitive(g):
    build(g, _base({"frontend": [], "catalog": []}, calls=[("frontend", "catalog")], deps=[("catalog", "libjson", "1.2.0", False, [_V("EVAL-3", "MEDIUM", 5.5)])]))
    trace = Trace()
    f = best_findings(scored_paths(trace, graph_name=g))
    got = (f[0]["tier"], f[0]["hops"], f[0]["confidence"]) if f else None
    return {"truth": {("EVAL-3", "catalog")}, "w": {(x["vuln"], x["service"]) for x in f}, "b": _present_pairs(g), "trace": trace,
            "expected": "tier exposed (no exploit signal), 1 hop, confidence inferred",
            "answer": f"tier {got[0]}, {got[1]} hop, {got[2]}" if got else "nothing reachable",
            "ok": got == ("exposed", 1, "inferred"), "baseline_ok": False, "baseline_answer": "reports the advisory with no tier, hop count or confidence"}


def s_sensitive(g):
    build(g, _base({"frontend": [], "checkout": [], "payment": ["card_data"]}, calls=[("frontend", "checkout"), ("checkout", "payment")], assets=CARD,
                   deps=[("payment", "libpay", "3.0.0", True, [_V("EVAL-4", "HIGH", 8.0)])]))
    trace = Trace()
    f = best_findings(scored_paths(trace, graph_name=g))
    got = (f[0]["hops"], f[0]["data"]) if f else None
    return {"truth": {("EVAL-4", "payment")}, "w": {(x["vuln"], x["service"]) for x in f}, "b": _present_pairs(g), "trace": trace,
            "expected": "EVAL-4 reachable on payment, 2 hops, the service reads card_data",
            "answer": f"{got[0]} hops, reads {', '.join(got[1])}" if got else "nothing reachable",
            "ok": got == (2, ["card_data"]), "baseline_ok": False, "baseline_answer": "lists EVAL-4 by CVSS only: no path and no data context"}


def _fix_graphs(g, before_vulns, after_vulns, extra_after=()):
    sv = {"frontend": [], "payment": ["card_data"]}
    kw = {"calls": [("frontend", "payment")], "assets": CARD}
    build(g, _base(sv, **kw, deps=[("frontend", "libnet", "1.0.0", True, before_vulns)]))
    build(g + "_after", _base(sv, **kw, deps=[("frontend", "libnet", "1.1.0", True, after_vulns), *extra_after]))


def _gate_result(g, expect_pass, expected):
    gate, trace, after = _gate_run(g, g + "_after")
    return {"trace": trace, "gate": gate, "expected": expected, "answer": _gate_text(gate),
            "ok": gate["passed"] == expect_pass and (not expect_pass or not after["kev_findings"]),
            "baseline_ok": expect_pass, "baseline_answer": "applies the fix as given (no gate to check anything)"}


def s_safe_fix(g):
    _fix_graphs(g, [_V("EVAL-5", "HIGH", 8.1, True, 0.9, "1.1.0")], [])
    return _gate_result(g, True, "gate passes: the KEV path is gone and nothing new appears")


def s_unsafe_kev(g):
    _fix_graphs(g, [_V("EVAL-6", "HIGH", 8.1, True, 0.9, "1.1.0")], [_V("EVAL-6B", "HIGH", 8.8, True, 0.95, "1.2.0")])
    return _gate_result(g, False, "gate blocks: the upgrade carries a different KEV advisory")


def s_unsafe_exposure(g):
    _fix_graphs(g, [_V("EVAL-7", "HIGH", 7.8, False, 0.02, "1.1.0")], [], extra_after=[("payment", "libcard", "1.0.0", True, [_V("EVAL-7B", "HIGH", 8.2)])])
    return _gate_result(g, False, "gate blocks: payment (reads card data) gains a new HIGH advisory")


def s_no_fix(g):
    build(g, _base({"frontend": []}, deps=[("frontend", "libold", "0.3.0", True, [_V("EVAL-8", "HIGH", 8.0, False, 0.01, None)])]))
    trace = Trace()
    chosen = choose(scored_paths(trace, graph_name=g), 5)
    return {"trace": trace, "expected": "abstain: no fixed version is published, so no upgrade is proposed",
            "answer": "abstained (no upgrade proposed)" if not chosen else f"proposed {len(chosen)} upgrade(s)", "ok": not chosen,
            "baseline_ok": False, "baseline_answer": "ranks EVAL-8 first and says to fix it, with no version to move to"}


def _priority(g, want, expected):
    trace = Trace()
    top = best_findings(scored_paths(trace, graph_name=g))[0]
    got, base = f"{top['vuln']} in {top['service']}", _cvss_top(g)
    return {"trace": trace, "expected": expected, "answer": got, "ok": got == want, "baseline_ok": base == want, "baseline_answer": base}


def s_close_cvss(g):
    build(g, _base({"frontend": [], "catalog": []}, calls=[("frontend", "catalog")], deps=[
        ("catalog", "libimg", "1.0.0", False, [_V("EVAL-9A", "HIGH", 7.5, False, 0.01)]),
        ("frontend", "libauth", "1.0.0", True, [_V("EVAL-9B", "HIGH", 7.4, False, 0.45)])]))
    return _priority(g, "EVAL-9B in frontend", "EVAL-9B in frontend first: 0 hops and a 45% EPSS signal outweigh a 0.1 higher CVSS one hop deeper")


def s_kev_vs_cvss(g):
    build(g, _base({"frontend": [], "catalog": [], "search": []}, calls=[("frontend", "catalog"), ("catalog", "search")], deps=[
        ("search", "libcrit", "1.0.0", False, [_V("EVAL-10A", "CRITICAL", 9.8, False, 0.01)]),
        ("search", "libkev", "1.0.0", False, [_V("EVAL-10B", "MEDIUM", 6.0, True, 0.2)])]))
    return _priority(g, "EVAL-10B in search", "EVAL-10B in search first: known exploitation (KEV) outranks a CRITICAL with no exploit signal at the same depth")


def s_choke(g):
    from warden.tools.topology import SENSITIVE_ROUTES_CYPHER, choke_analysis

    pii = {"customer_email": (3, "PII"), "address": (3, "PII")}
    build(g, _base({"frontend": [], "checkout": [], "payment": ["card_data"], "mail": ["customer_email"], "ship": ["address"]},
                   calls=[("frontend", "checkout"), ("checkout", "payment"), ("checkout", "mail"), ("frontend", "ship")], assets={**CARD, **pii}))
    trace = Trace()
    a = choke_analysis(trace.ro(SENSITIVE_ROUTES_CYPHER, {"weight": 3}, g), 3)
    top = a["rows"][0]
    got = f"{top['service']} ({top['paths']} of {a['total']} paths)"
    return {"trace": trace, "expected": "checkout first: 2 of 3 internet-to-sensitive-data paths go through it", "answer": got, "ok": top["service"] == "checkout" and top["paths"] == 2 and a["total"] == 3,
            "baseline_ok": False, "baseline_answer": "has no path model; ranks services by their own highest CVSS, not by the paths through them"}


def s_stale(g):
    from warden import memory

    d = {"id": "dec_eval", "status": "approved", "at": 1_000, "sha": "old-commit", "items": [{"package": "libx", "from": "1.0.0", "to": "2.0.0", "services": ["frontend"]}]}
    versions = {"libx": {"frontend": {"1.0.0"}}}
    same = memory.applies_now(d, versions, "old-commit", 2_000)["state"]
    stale = memory.applies_now(d, versions, "new-commit", 2_000)["state"]
    return {"trace": Trace(), "expected": "fresh on the same commit, stale (re-gated) once the graph is re-read from another commit", "answer": f"{same} on the same commit, {stale} on a new one",
            "ok": (same, stale) == ("fresh", "stale"), "baseline_ok": False, "baseline_answer": "reuses the old approval as is; it has no memory of what the graph looked like"}


PENDING = [
    ("contradiction", "Lockfile and Dockerfile disagree on a version", "Warden abstains and flags the contradiction", "Phase 1d: contradiction detection"),
]

SCENARIOS = [
    ("reachable_direct", "Reachable direct dependency on the entry service", "reachability", s_reachable_direct),
    ("unreachable", "Vulnerable package in a service nothing calls", "reachability", s_unreachable),
    ("transitive", "Advisory one hop behind the entry service", "reachability", s_transitive),
    ("sensitive_path", "Entry service to card data in two hops", "reachability", s_sensitive),
    ("safe_fix", "Safe fix removes a KEV path", "gate", s_safe_fix),
    ("unsafe_kev", "Fix that introduces a different KEV advisory", "gate", s_unsafe_kev),
    ("unsafe_exposure", "Fix that exposes card data to a new HIGH advisory", "gate", s_unsafe_exposure),
    ("no_fix", "No fixed version published", "abstain", s_no_fix),
    ("close_cvss", "Nearly equal CVSS, different exposure and exploit signal", "priority", s_close_cvss),
    ("kev_vs_cvss", "KEV MEDIUM against a CRITICAL with no exploit signal", "priority", s_kev_vs_cvss),
    ("choke_point", "One service carries most paths to card and personal data", "choke", s_choke),
    ("stale_decision", "A past approval after the graph was re-read from another commit", "memory", s_stale),
]


def _pct(n: float, d: float):
    return None if not d else round(100 * n / d)


def _percentile(xs: list[float], q: float):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 1) if xs else None


def run() -> dict:
    t0 = time.perf_counter()
    results, lat = [], []
    reach = {"w": {"tp": 0, "fp": 0, "fn": 0}, "b": {"tp": 0, "fp": 0, "fn": 0}}
    for sid, title, cat, fn in SCENARIOS:
        g = f"eval_{sid}"
        try:
            r = fn(g)
        except Exception as e:  # a failing scenario is reported, never hidden
            results.append({"id": sid, "title": title, "category": cat, "status": "error", "error": str(e)[:200]})
            continue
        finally:
            for name in (g, g + "_after"):
                try:
                    delete_graph(name)
                except Exception:
                    pass
        if "truth" in r:
            cw, cb = _counts(r["w"], r["truth"]), _counts(r["b"], r["truth"])
            for k, c in (("w", cw), ("b", cb)):
                for m in c:
                    reach[k][m] += c[m]
            r.setdefault("ok", cw["fp"] == 0 and cw["fn"] == 0)
            r.setdefault("baseline_ok", cb["fp"] == 0 and cb["fn"] == 0)
            r.setdefault("baseline_answer", f"every present advisory reported, none filtered by reachability: {_pairs_text(r['b'])}")
        ms = [q["ms"] for q in r["trace"].queries]
        lat += ms
        results.append({
            "id": sid, "title": title, "category": cat, "status": "ran", "expected": r["expected"],
            "warden": {"answer": r["answer"], "ok": bool(r["ok"])},
            "baseline": {"answer": r["baseline_answer"], "ok": bool(r["baseline_ok"])},
            "queries": len(ms), "ms": round(sum(ms), 1),
            "checks": [{"check": c["check"], "ok": c["ok"], "level": c["level"], "detail": c["detail"]} for c in r["gate"]["checks"]] if "gate" in r else None,
        })
    ran = [r for r in results if r["status"] == "ran"]

    def cat(c):
        xs = [r for r in ran if r["category"] == c]
        return {"n": len(xs), "warden": sum(r["warden"]["ok"] for r in xs), "baseline": sum(r["baseline"]["ok"] for r in xs)}

    def pr(c):
        return {**c, "precision": _pct(c["tp"], c["tp"] + c["fp"]), "recall": _pct(c["tp"], c["tp"] + c["fn"])}

    out = {
        "at": int(time.time() * 1000), "seconds": round(time.perf_counter() - t0, 1),
        "scenarios": results,
        "pending": [{"id": i, "title": t, "expected": e, "unlocks": u, "status": "pending"} for i, t, e, u in PENDING],
        "metrics": {
            "reachability": {"warden": pr(reach["w"]), "baseline": pr(reach["b"])},
            "priority": cat("priority"), "gate": cat("gate"), "abstain": cat("abstain"), "choke": cat("choke"), "memory": cat("memory"),
            "overall": {"n": len(ran), "warden": sum(r["warden"]["ok"] for r in ran), "baseline": sum(r["baseline"]["ok"] for r in ran)},
            "latency_ms": {"queries": len(lat), "p50": _percentile(lat, 0.5), "p95": _percentile(lat, 0.95)},
        },
        "baseline_definition": "A severity-only scanner: ranks every present advisory by CVSS, has no reachability, no remediation gate and never abstains.",
        "limitations": "Known answers are authored from each scenario's construction. This measures designed behaviour on controlled topologies, not third-party data.",
    }
    _LAST.clear()
    _LAST.update(out)
    return out


def last() -> dict | None:
    return dict(_LAST) if _LAST else None
