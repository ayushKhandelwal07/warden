"""Attack-path regression tests for a remediation plan.

Before a fix, record the paths that matter (the invariants). After rehearsing the fix on a graph copy, re-run the same
analysis and classify every invariant as removed, still present, or new. Paths are compared by *semantic identity*
(advisory × service, or service × data asset), never by node-id sequences, so a harmless reshaping of a path is not
mistaken for a removed attack path.

Invariant kinds
  kev        a reachable advisory with CISA-reported exploitation, per service              key: (advisory, service)
  sensitive  a reachable advisory in a service that reads PCI/PII data                      key: (advisory, service)
  data       a service that reads PCI/PII data and still has any reachable exposure         key: (service, data asset)
"""
SENSITIVE_WEIGHT = 3  # PCI (5) and PII (3); ORDER and SESSION data are weight 2


def sensitive_assets(trace, graph_name=None) -> dict[str, dict]:
    rows = trace.ro("MATCH (d:DataAsset) WHERE d.weight >= $w RETURN d.name AS name, d.sensitivity AS sensitivity, d.weight AS weight", {"w": SENSITIVE_WEIGHT}, graph_name)
    return {r["name"]: r for r in rows}


def invariants(findings: list[dict], assets: dict[str, dict]) -> dict[str, dict[tuple, dict]]:
    """`findings` = best_findings(scored_paths(...)): one entry per (advisory, service)."""
    kev, sensitive, data = {}, {}, {}
    for f in findings:
        key = (f["vuln"], f["service"])
        if f["kev"]:
            kev[key] = f
        touched = [a for a in (f.get("data") or []) if a in assets]
        if touched:
            sensitive[key] = f
            for a in touched:
                cur = data.get((f["service"], a))
                data[(f["service"], a)] = {**(cur or {}), "service": f["service"], "asset": a, "exposures": (cur or {}).get("exposures", 0) + 1,
                                           "sensitivity": assets[a]["sensitivity"]}
    return {"kev": kev, "sensitive": sensitive, "data": data}


def _row(kind: str, key: tuple, before: dict | None, after: dict | None) -> dict:
    src = before or after or {}
    if kind == "data":
        return {"service": key[0], "asset": key[1], "sensitivity": src.get("sensitivity"),
                "exposures_before": (before or {}).get("exposures", 0), "exposures_after": (after or {}).get("exposures", 0)}
    return {"vuln": key[0], "service": key[1], "severity": src.get("severity"), "kev": bool(src.get("kev")), "tier": src.get("tier"), "risk_before": (before or {}).get("risk"),
            "risk_after": (after or {}).get("risk"), "package_before": (before or {}).get("package"), "package_after": (after or {}).get("package")}


def classify(before: dict[str, dict], after: dict[str, dict]) -> dict:
    """removed = in before, not after · remaining = in both · new = in after only. Each kind is reported separately."""
    out = {}
    for kind in before:
        b, a = before[kind], after[kind]
        out[kind] = {
            "before": len(b),
            "after": len(a),
            "removed": [_row(kind, k, b[k], None) for k in sorted(b.keys() - a.keys())],
            "remaining": [_row(kind, k, b[k], a[k]) for k in sorted(b.keys() & a.keys())],
            "new": [_row(kind, k, None, a[k]) for k in sorted(a.keys() - b.keys())],
        }
    return out


def exposed_services(findings: list[dict]) -> set[str]:
    return {f["service"] for f in findings}
