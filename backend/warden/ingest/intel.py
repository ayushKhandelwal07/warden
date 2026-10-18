"""Threat intel: CISA KEV (exploited in the wild), FIRST EPSS (exploit probability),
and NVD CVSS as a fallback score for advisories OSV has no CVSS for."""
import time

from warden.ingest.common import cached_json, http_get_json

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss?cve="
NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId="


def load_kev(refresh: bool = False) -> dict[str, dict]:
    data = cached_json("kev", "catalog", lambda: http_get_json(KEV_URL), refresh)
    return {v["cveID"]: v for v in data["vulnerabilities"]}


def kev_meta() -> dict:
    data = cached_json("kev", "catalog", lambda: http_get_json(KEV_URL))
    return {"version": data.get("catalogVersion"), "released": data.get("dateReleased"), "count": data.get("count")}


def load_epss(cves: list[str], refresh: bool = False) -> dict[str, dict]:
    out = {}
    cves = sorted(set(cves))
    for i in range(0, len(cves), 80):
        chunk = cves[i : i + 80]
        data = cached_json("epss", ",".join(chunk), lambda: http_get_json(EPSS_URL + ",".join(chunk)), refresh)
        for row in data.get("data", []):
            out[row["cve"]] = {"epss": float(row["epss"]), "percentile": float(row["percentile"]), "date": row.get("date")}
    return out


def nvd_cvss(cve: str) -> tuple[float | None, str | None]:
    """Highest NVD base score for a CVE (cached; NVD allows ~5 unauthenticated requests / 30s)."""

    def fetch():
        time.sleep(6.5)
        return http_get_json(NVD_URL + cve)

    data = cached_json("nvd", cve, fetch)
    best = (None, None)
    for item in data.get("vulnerabilities", []):
        metrics = item.get("cve", {}).get("metrics", {})
        for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30"):
            for m in metrics.get(key, []):
                d = m.get("cvssData", {})
                sc = d.get("baseScore")
                if sc is not None and (best[0] is None or sc > best[0]):
                    best = (float(sc), d.get("vectorString"))
    return best


def enrich(vulns: list[dict], use_nvd: bool = True) -> dict:
    """Adds kev/epss (+ NVD cvss fallback) to vulnerability dicts in place."""
    kev = load_kev()
    all_cves = [c for v in vulns for c in v.get("cves", [])]
    epss = load_epss(all_cves)
    stats = {"kev": 0, "epss": 0, "nvd_filled": 0}
    for v in vulns:
        cves = v.get("cves", [])
        hits = [kev[c] for c in cves if c in kev]
        v["kev"] = bool(hits)
        if hits:
            h = hits[0]
            v.update(
                kev_cve=h["cveID"],
                kev_name=h.get("vulnerabilityName"),
                kev_added=h.get("dateAdded"),
                kev_due=h.get("dueDate"),
                kev_ransomware=h.get("knownRansomwareCampaignUse") == "Known",
            )
            stats["kev"] += 1
        scores = [epss[c] for c in cves if c in epss]
        if scores:
            top = max(scores, key=lambda s: s["epss"])
            v["epss"], v["epss_percentile"] = top["epss"], top["percentile"]
            stats["epss"] += 1
        else:
            v["epss"], v["epss_percentile"] = None, None
        if v.get("cvss") is None and cves and use_nvd:
            for c in cves:
                sc, vec = nvd_cvss(c)
                if sc is not None:
                    v["cvss"], v["cvss_vector"] = sc, vec
                    v["severity"] = "CRITICAL" if sc >= 9 else "HIGH" if sc >= 7 else "MEDIUM" if sc >= 4 else "LOW"
                    v["cvss_source"] = "nvd"
                    stats["nvd_filled"] += 1
                    break
        if v.get("severity") is None:
            v["severity"] = "UNKNOWN"
    return stats


def freshness() -> dict:
    """When each external feed was last retrieved (the on-disk cache's modification time, UTC ISO), so a reader can see
    how old the threat intelligence behind a conclusion is. None when a feed was never fetched on this machine."""
    from datetime import datetime, timezone

    from warden.ingest.common import _cache_path

    def when(ns: str, key: str):
        p = _cache_path(ns, key)
        return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(timespec="seconds") if p.exists() else None

    epss = sorted((_cache_path("epss", "x").parent).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    epss_at = datetime.fromtimestamp(epss[0].stat().st_mtime, timezone.utc).isoformat(timespec="seconds") if epss else None
    return {"kev": when("kev", "catalog"), "epss": epss_at}
