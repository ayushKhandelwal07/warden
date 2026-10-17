"""Risk of one attack path, explained factor by factor (no hidden model).

risk = 50 × severity × exploit × exposure × data   (0–100)
  severity  CVSS/10, or a label default when no score exists
  exploit   1.0 if on CISA KEV, else 0.1 + 0.9 × EPSS (exploit probability, next 30 days)
  exposure  0.5 ^ hops: an attacker talks to the internet-facing service directly, but to
            internal services only through that service's own calls
  data      1 + (max sensitivity weight of data the service reads) / 5   (1.0–2.0)
"""

SEVERITY_DEFAULT = {"CRITICAL": 0.95, "HIGH": 0.8, "MEDIUM": 0.55, "LOW": 0.3, "UNKNOWN": 0.5}


def risk_factors(severity: str | None, cvss: float | None, kev: bool, epss: float | None, hops: int | None, data_weight: float | None) -> dict:
    sev = (cvss / 10.0) if cvss else SEVERITY_DEFAULT.get(severity or "UNKNOWN", 0.5)
    exploit = 1.0 if kev else 0.1 + 0.9 * (epss or 0.0)
    exposure = 0.0 if hops is None else 0.5 ** hops
    data = 1.0 + (data_weight or 0) / 5.0
    score = round(50 * sev * exploit * exposure * data, 1)
    factors = {"severity": round(sev, 2), "exploit": round(exploit, 3), "exposure": round(exposure, 3), "data": round(data, 2)}
    # The factor that moved this score most (furthest from neutral) is what the agent cites.
    deltas = {"severity": abs(sev - 0.6), "exploit": abs(exploit - 0.1) * 1.5, "exposure": abs(1 - exposure), "data": abs(data - 1.0)}
    driver = max(deltas, key=deltas.get)
    return {"risk": score, "factors": factors, "driver": driver}
