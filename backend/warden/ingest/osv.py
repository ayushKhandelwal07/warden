"""OSV.dev -> Vulnerability, AFFECTED_BY {fixed}. All responses cached on disk."""
import re
from concurrent.futures import ThreadPoolExecutor

from cvss import CVSS3, CVSS4

from warden.ingest.common import cached_json, http_get_json, http_post_json, version_key

OSV = "https://api.osv.dev/v1"
LABEL_FROM_DB = {"CRITICAL": "CRITICAL", "HIGH": "HIGH", "MODERATE": "MEDIUM", "MEDIUM": "MEDIUM", "LOW": "LOW"}


def _query_ids(packages: list[dict], refresh: bool) -> dict[str, list[str]]:
    """package key -> OSV ids affecting that exact version."""
    out = {}
    for i in range(0, len(packages), 500):
        chunk = packages[i : i + 500]
        body = {
            "queries": [
                {"package": {"name": p["name"], "ecosystem": p["ecosystem"]}, "version": p["version"].lstrip("v") if p["name"] == "stdlib" else p["version"]}
                for p in chunk
            ]
        }
        key = "batch-" + str(abs(hash(tuple(p["key"] for p in chunk))))
        res = cached_json("osv_batch", key + f"-{len(chunk)}", lambda: http_post_json(f"{OSV}/querybatch", body), refresh)
        for p, r in zip(chunk, res["results"]):
            out[p["key"]] = [v["id"] for v in r.get("vulns", [])]
    return out


def _details(ids: set[str], refresh: bool) -> dict[str, dict]:
    def one(i):
        return i, cached_json("osv_vuln", i, lambda: http_get_json(f"{OSV}/vulns/{i}"), refresh)

    with ThreadPoolExecutor(16) as ex:
        return dict(ex.map(one, sorted(ids)))


def _score(rec: dict) -> tuple[float | None, str | None]:
    best, vec = None, None
    for s in rec.get("severity", []) or []:
        try:
            if s["type"] == "CVSS_V3":
                sc = float(CVSS3(s["score"]).scores()[0])
            elif s["type"] == "CVSS_V4":
                sc = float(CVSS4(s["score"]).base_score)
            else:
                continue
        except Exception:
            continue
        if best is None or sc > best:
            best, vec = sc, s["score"]
    return best, vec


def _label(score: float | None, rec: dict) -> str | None:
    if score is not None:
        return "CRITICAL" if score >= 9 else "HIGH" if score >= 7 else "MEDIUM" if score >= 4 else "LOW" if score > 0 else None
    db = (rec.get("database_specific") or {}).get("severity")
    return LABEL_FROM_DB.get(str(db).upper()) if db else None


def _cve_key(cve: str) -> tuple:
    m = re.match(r"CVE-(\d+)-(\d+)", cve)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _canonical(rec: dict) -> str:
    """Canonical id = the newest CVE alias (merged advisories list older, related CVEs too), else GHSA, else OSV id."""
    ids = [rec["id"], *rec.get("aliases", [])]
    cves = sorted((i for i in ids if i.startswith("CVE-")), key=_cve_key, reverse=True)
    if cves:
        return cves[0]
    ghsa = sorted(i for i in ids if i.startswith("GHSA-"))
    return ghsa[0] if ghsa else rec["id"]


def _fixed_version(rec: dict, pkg: dict) -> str | None:
    installed = version_key(pkg["version"])
    candidates = []
    for aff in rec.get("affected", []):
        ap = aff.get("package", {})
        if ap.get("name") != pkg["name"] or ap.get("ecosystem", "").split(":")[0] != pkg["ecosystem"]:
            continue
        for rng in aff.get("ranges", []):
            if rng.get("type") == "GIT":
                continue
            lo, events = None, rng.get("events", [])
            for ev in events:
                if "introduced" in ev:
                    lo = ev["introduced"]
                elif "fixed" in ev:
                    fx = ev["fixed"]
                    in_range = (lo in (None, "0") or version_key(lo) <= installed) and installed < version_key(fx)
                    if in_range:
                        return fx
                    if version_key(fx) > installed:
                        candidates.append(fx)
    return min(candidates, key=version_key) if candidates else None


def fetch_vulnerabilities(packages: list[dict], refresh: bool = False) -> dict:
    ids_by_pkg = _query_ids(packages, refresh)
    recs = _details({i for ids in ids_by_pkg.values() for i in ids}, refresh)

    # Go/PyPI advisories often carry no CVSS; borrow it from their GHSA alias.
    alias_ids = set()
    for r in recs.values():
        if _score(r)[0] is None:
            alias_ids |= {a for a in r.get("aliases", []) if a.startswith("GHSA-") and a not in recs}
    alias_recs = _details(alias_ids, refresh) if alias_ids else {}

    vulns: dict[str, dict] = {}
    for osv_id, r in recs.items():
        cid = _canonical(r)
        score, vec = _score(r)
        if score is None:
            for a in r.get("aliases", []):
                if a in alias_recs or a in recs:
                    score, vec = _score(alias_recs.get(a) or recs[a])
                    if score is not None:
                        break
        v = vulns.setdefault(
            cid,
            {
                "id": cid,
                "osv_ids": [],
                "aliases": set(),
                "summary": r.get("summary") or (r.get("details") or "")[:200],
                "published_at": r.get("published"),
                "cvss": None,
                "cvss_vector": None,
                "severity": None,
                "url": f"https://osv.dev/vulnerability/{osv_id}",
            },
        )
        v["osv_ids"].append(osv_id)
        v["aliases"] |= set(r.get("aliases", [])) | {osv_id}
        if score is not None and (v["cvss"] is None or score > v["cvss"]):
            v["cvss"], v["cvss_vector"] = score, vec
        label = _label(score, r)
        order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        if label and (v["severity"] is None or order.index(label) > order.index(v["severity"])):
            v["severity"] = label
        if not v["summary"] and r.get("summary"):
            v["summary"] = r["summary"]

    pkg_by_key = {p["key"]: p for p in packages}
    affected = {}
    for key, ids in ids_by_pkg.items():
        for osv_id in ids:
            cid = _canonical(recs[osv_id])
            fx = _fixed_version(recs[osv_id], pkg_by_key[key])
            cur = affected.get((key, cid))
            if cur is None or (fx and (cur["fixed"] is None or version_key(fx) > version_key(cur["fixed"]))):
                affected[(key, cid)] = {"key": key, "vuln": cid, "fixed": fx, "osv_id": osv_id}

    for v in vulns.values():
        v["aliases"] = sorted(v["aliases"])
        v["cves"] = [a for a in v["aliases"] if a.startswith("CVE-")]
        v["osv_ids"] = sorted(set(v["osv_ids"]))
    return {"vulns": list(vulns.values()), "affected": list(affected.values())}
