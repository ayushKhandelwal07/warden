"""Constrained plan optimizer: several candidate remediation plans, each rehearsed on its own graph copy, compared side by side.

Strategies (all greedy set cover over the same scored paths, differing in what they are allowed to do):
  kev_only    the fewest changes that cover every CISA KEV exposure
  safest      no major-version bumps; most risk removed within the change budget
  max_risk    most risk removed within the change budget, majors allowed (unless the constraints forbid them)
  balanced    KEV first, then largest remaining risk, capped at half the budget

Constraints (all optional): max_changes, frozen_services (a package that any frozen service ships cannot change, because an
upgrade applies to every service shipping it), no_major, must_fix_kev.

Every number in the table comes from a real rehearsal, not an estimate. The gate verdict is the deterministic gate.
"""
from warden import planner
from warden.actions import patches
from warden.tools.base import Trace
from warden.tools.security import best_findings, scored_paths

STRATEGIES = {
    "kev_only": ("Fewest changes", "Only what is needed to cover every CISA KEV exposure"),
    "safest": ("Safest", "No major-version bumps; most risk removed within the budget"),
    "balanced": ("Balanced", "KEV first, then the largest remaining risk, at half the budget"),
    "max_risk": ("Most risk removed", "Largest risk reduction within the budget"),
}


def _norm(c: dict | None) -> dict:
    c = c or {}
    return {
        "max_changes": max(1, min(8, int(c.get("max_changes") or 5))),
        "frozen_services": sorted({str(s) for s in (c.get("frozen_services") or []) if s}),
        "no_major": bool(c.get("no_major")),
        "must_fix_kev": c.get("must_fix_kev", True) is not False,
    }


def _usable(paths: list[dict], cons: dict) -> list[dict]:
    """Drop every path on a package that a frozen service ships (the upgrade could not be applied to that service)."""
    frozen = set(cons["frozen_services"])
    blocked = {p["package_key"] for p in paths if p["service"] in frozen}
    return [p for p in paths if p["package_key"] not in blocked]


def _cover_kev(paths, cap):
    """The fewest packages that cover every KEV exposure (greedy by KEV exposures covered)."""
    need = {(p["vuln"], p["service"]) for p in paths if p["kev"]}
    cands = [c for c in planner._candidates(paths) if any(p["kev"] for p in c["removable"])]
    chosen, left = [], set(need)
    while left and cands and len(chosen) < cap:
        best = max(cands, key=lambda c: len({(p["vuln"], p["service"]) for p in c["removable"] if p["kev"]} & left))
        gain = {(p["vuln"], p["service"]) for p in best["removable"] if p["kev"]} & left
        if not gain:
            break
        chosen.append(best)
        left -= gain
        cands = [c for c in cands if c is not best]
    return chosen


def select(strategy: str, constraints: dict | None, paths: list[dict] | None = None) -> list[dict]:
    cons = _norm(constraints)
    paths = _usable(paths if paths is not None else scored_paths(Trace()), cons)
    cap = cons["max_changes"]

    def drop_majors(ps):
        majors = {c["package_key"] for c in planner._candidates(ps) if patches.major_bump(c["from"], c["to_version"])}
        return [p for p in ps if p["package_key"] not in majors]

    if strategy == "kev_only":
        pool = drop_majors(paths) if cons["no_major"] else paths
        chosen = _cover_kev(pool, cap)
        return planner.choose([p for p in pool if p["package_key"] in {c["package_key"] for c in chosen}], len(chosen)) if chosen else []
    if strategy == "safest":
        return planner.choose(drop_majors(paths), cap)
    if strategy == "balanced":
        return planner.choose(drop_majors(paths) if cons["no_major"] else paths, max(1, cap // 2))
    return planner.choose(drop_majors(paths) if cons["no_major"] else paths, cap)


def _dominates(a: dict, b: dict) -> bool:
    ka = (-a["risk_removed"], a["changes"], a["majors"], a["new_advisories"], a["residual_kev"])
    kb = (-b["risk_removed"], b["changes"], b["majors"], b["new_advisories"], b["residual_kev"])
    return all(x <= y for x, y in zip(ka, kb)) and ka != kb


def _shared_win(paths: list[dict], chosen: list[dict]) -> dict | None:
    """The upgrade that clears the most exposures across the most services, against fixing only the top-CVSS advisory."""
    if not chosen:
        return None
    top = max(chosen, key=lambda c: len({(p["vuln"], p["service"]) for p in c["removable"]}))
    exposures = {(p["vuln"], p["service"]) for p in top["removable"]}
    findings = best_findings(paths)
    worst = max(findings, key=lambda f: (f["cvss"] or 0)) if findings else None
    return {
        "package": top["package"], "to": top["to_version"], "exposures": len(exposures), "services": len({s for _, s in exposures}),
        "vulns": len({v for v, _ in exposures}),
        "top_cvss": {"vuln": worst["vuln"], "service": worst["service"], "cvss": worst["cvss"]} if worst else None,
    }


def compare(constraints: dict | None = None) -> dict:
    cons = _norm(constraints)
    paths = scored_paths(Trace())
    rows, seen = [], {}
    for sid, (label, why) in STRATEGIES.items():
        chosen = select(sid, cons, paths)
        sig = tuple(sorted(c["package_key"] for c in chosen))
        if not chosen:
            rows.append({"id": sid, "label": label, "why": why, "empty": True, "same_as": None})
            continue
        if sig in seen:  # same upgrades as an earlier strategy: not rehearsed twice
            rows.append({"id": sid, "label": label, "why": why, "same_as": seen[sig]})
            continue
        plan = planner.build_plan(len(chosen), chosen_override=chosen)
        b, a = plan["before"], plan["after"]
        majors = sum(1 for i in plan["items"] if patches.major_bump(i["from"], i["to"]))
        row = {
            "id": sid, "label": label, "why": why, "same_as": None, "empty": False,
            "risk_before": b["risk"], "risk_after": a["risk"], "risk_removed": round(b["risk"] - a["risk"], 1),
            "risk_removed_pct": round(100 * (b["risk"] - a["risk"]) / b["risk"]) if b["risk"] else 0,
            "changes": len(plan["items"]), "majors": majors, "new_advisories": len(plan["new_advisories_on_upgraded_versions"]),
            "exposures_removed": len(plan["removed"]), "residual_kev": a["kev_findings"], "kev_before": b["kev_findings"],
            "gate": plan["gate"]["passed"], "gate_failed": [c["check"] for c in plan["gate"]["checks"] if not c["ok"] and c["level"] == "block"],
            "items": [{"package": i["package"], "from": i["from"], "to": i["to"], "services": i["services"], "kev": i["kev"], "major": patches.major_bump(i["from"], i["to"]),
                       "risk_removed": i["risk_removed"]} for i in plan["items"]],
            "shared_win": _shared_win(paths, chosen),
        }
        rows.append(row)
        seen[sig] = sid
    real = [r for r in rows if not r.get("empty") and not r.get("same_as")]
    for r in real:
        r["pareto"] = not any(_dominates(o, r) for o in real if o is not r)
    kev_ok = [r for r in real if r["gate"] and (not cons["must_fix_kev"] or r["residual_kev"] == 0)]
    pick = max(kev_ok, key=lambda r: (r["pareto"], r["risk_removed"] - 3 * r["changes"] - 5 * r["majors"]), default=None)
    if pick:
        pick["recommended"] = True
    return {"constraints": cons, "rows": rows, "recommended": pick["id"] if pick else None,
            "note": "Each row was rehearsed on its own copy of the graph. Pareto = no other row is at least as good on every column and better on one."}
