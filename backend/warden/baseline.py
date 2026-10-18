"""A fair comparison: what a severity-only scanner would fix first vs what Warden's graph-informed score says.

Both rankings are over the *same universe* (every graph-reachable advisory × service exposure) on the *same snapshot*.

  baseline  CVSS base score, highest first (ties broken by advisory id, then service, so it is deterministic)
  kev-aware CISA KEV advisories first, then CVSS (what a threat-intel-aware scanner does): a stronger, fairer baseline
  graph     Warden's risk = 50 × severity × exploit × exposure × data  (see tools/risk.py)

Nothing here is tuned to make the graph look good: the numbers are whatever the two rankings produce.
"""
from warden.tools.base import Trace
from warden.tools.security import best_findings, scored_paths


def _cvss(f: dict) -> float:
    return float(f["cvss"]) if f.get("cvss") is not None else {"CRITICAL": 9.5, "HIGH": 7.5, "MEDIUM": 5.0, "LOW": 2.0}.get(f["severity"], 0.0)


def _reason_graph_lower(f: dict) -> list[str]:
    out = []
    if f["hops"]:
        out.append(f"{f['hops']} hop(s) behind the internet-facing service (exposure ×{f['factors']['exposure']})")
    if f["tier"] == "exposed":
        out.append(f"no exploit signal (EPSS {(f['epss'] or 0):.1%})")
    if not f["data"]:
        out.append("the service reads no sensitive data")
    return out or ["severity is high but nothing else raises the risk"]


def _reason_graph_higher(f: dict) -> list[str]:
    out = []
    if f["kev"]:
        out.append("on CISA KEV (known exploitation reported)")
    elif f["tier"] == "exploit_signal":
        out.append(f"exploit signal (EPSS {(f['epss'] or 0):.1%})")
    if f["hops"] == 0:
        out.append("on the internet-facing service itself (0 hops)")
    if f.get("data_weight") and f["data_weight"] >= 3:
        out.append(f"the service reads {', '.join(f['data'])}")
    return out or ["a higher combined exploit, exposure and data factor"]


def _row(f: dict, base_rank: int, graph_rank: int) -> dict:
    lower = graph_rank > base_rank
    return {
        "vuln": f["vuln"], "service": f["service"], "package": f["package"], "severity": f["severity"], "cvss": f["cvss"],
        "risk": f["risk"], "tier": f["tier"], "kev": f["kev"], "epss": f["epss"], "hops": f["hops"], "data": f["data"],
        "baseline_rank": base_rank, "graph_rank": graph_rank,
        "why": (_reason_graph_lower(f) if lower else _reason_graph_higher(f)) if base_rank != graph_rank else ["same position in both rankings"],
    }


def compare(findings: list[dict] | None = None, n: int = 10) -> dict:
    findings = findings if findings is not None else best_findings(scored_paths(Trace()))
    by_base = sorted(findings, key=lambda f: (-_cvss(f), f["vuln"], f["service"]))
    by_graph = sorted(findings, key=lambda f: (-f["risk"], f["vuln"], f["service"]))
    key = lambda f: (f["vuln"], f["service"])  # noqa: E731
    base_rank = {key(f): i + 1 for i, f in enumerate(by_base)}
    graph_rank = {key(f): i + 1 for i, f in enumerate(by_graph)}
    row = lambda f: _row(f, base_rank[key(f)], graph_rank[key(f)])  # noqa: E731

    by_kev = sorted(findings, key=lambda f: (not f["kev"], -_cvss(f), f["vuln"], f["service"]))
    kev_top = {key(f) for f in by_kev[:n]}
    base_top = {key(f) for f in by_base[:n]}
    graph_top = {key(f) for f in by_graph[:n]}
    overlap = base_top & graph_top

    # Where would a severity-only scanner put the exposures with reported exploitation?
    kev = [{**row(f)} for f in by_graph if f["kev"]]

    # The clearest reversal: two exposures with nearly the same CVSS where the graph ranks the other one much higher.
    best = None
    pool = by_graph[:60]
    for a in by_base:  # a: the scanner's pick
        for b in pool:
            if key(a) == key(b) or abs(_cvss(a) - _cvss(b)) > 1.0 or _cvss(a) < _cvss(b):
                continue
            ratio = b["risk"] / a["risk"] if a["risk"] else float("inf")
            if ratio >= 2 and (best is None or ratio > best[0]):
                best = (ratio, a, b)
        if best and _cvss(a) < by_base[0]["cvss"] - 3:
            break
    headline = None
    if best:
        _, a, b = best
        headline = {"scanner_pick": row(a), "graph_pick": row(b), "cvss_gap": round(abs(_cvss(a) - _cvss(b)), 1),
                    "risk_ratio": round(best[0], 1)}

    return {
        "universe": len(findings),
        "n": n,
        "method": {
            "unit": "advisory × service exposure, graph-reachable, one snapshot",
            "baseline": "CVSS base score, highest first; ties by advisory id then service",
            "kev_aware": "CISA KEV exposures first, then CVSS",
            "graph": "Warden risk = 50 × severity × exploit × exposure × data",
        },
        "kev_aware": {
            "top": [row(f) for f in by_kev[:n]],
            "overlap": len(kev_top & graph_top),
            "only_graph": [row(f) for f in by_graph[:n] if key(f) not in kev_top],
            "only_kev_aware": [row(f) for f in by_kev[:n] if key(f) not in graph_top],
        },
        "baseline_top": [row(f) for f in by_base[:n]],
        "graph_top": [row(f) for f in by_graph[:n]],
        "overlap": len(overlap),
        "only_baseline": [row(f) for f in by_base[:n] if key(f) not in graph_top],
        "only_graph": [row(f) for f in by_graph[:n] if key(f) not in base_top],
        "kev_positions": kev,
        "headline": headline,
    }
