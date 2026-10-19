"""What the graph knows about the org around the code: owners, sensitive data, policies and past incidents.

The curated files in backend/org/ describe microservices-demo, so they only apply when the repo is that codebase (most of
its services are found). For any other repo nothing is made up:
  - owners come from CODEOWNERS, when the repo has one;
  - sensitive data is inferred from what a service depends on (a payment SDK reads card data, a JWT or password-hashing
    library handles credentials, a database driver holds records), with the package as evidence on the READS edge;
  - the remediation policies are org-wide rules, so they apply everywhere;
  - there are no incidents.
"""
import fnmatch
from pathlib import Path

import yaml

from warden import config

# (asset, sensitivity, weight, description, packages that imply it). Names match by package name, or by Go module prefix.
DATA_SIGNALS = [
    ("CardData", "PCI", 5, "Payment card data handled through a payment provider's SDK.",
     {"stripe", "@stripe/stripe-js", "braintree", "@paypal/checkout-server-sdk", "paypal-rest-sdk", "razorpay", "square", "adyen",
      "github.com/stripe/stripe-go", "com.stripe:stripe-java", "stripe-ruby"}),
    ("Credentials", "AUTH", 4, "User passwords, tokens or sessions.",
     {"jsonwebtoken", "jose", "bcrypt", "bcryptjs", "argon2", "passport", "next-auth", "@auth/core", "express-session", "firebase-admin",
      "@clerk/clerk-sdk-node", "pyjwt", "passlib", "flask-login", "django-allauth", "authlib", "github.com/golang-jwt/jwt",
      "golang.org/x/crypto", "io.jsonwebtoken:jjwt", "org.springframework.boot:spring-boot-starter-security", "devise", "jwt"}),
    ("CustomerEmail", "PII", 3, "Email addresses used to contact users.",
     {"nodemailer", "@sendgrid/mail", "sendgrid", "mailgun.js", "postmark", "resend", "flask-mail", "django-anymail"}),
    ("DatabaseRecords", "DATA", 3, "Records the service reads from and writes to its database.",
     {"mongoose", "mongodb", "pg", "mysql", "mysql2", "sequelize", "@prisma/client", "prisma", "typeorm", "knex", "drizzle-orm",
      "redis", "ioredis", "sqlalchemy", "psycopg2", "psycopg2-binary", "psycopg", "pymongo", "motor", "django", "redis-py",
      "gorm.io/gorm", "github.com/lib/pq", "github.com/jackc/pgx", "go.mongodb.org/mongo-driver", "github.com/go-sql-driver/mysql",
      "github.com/redis/go-redis", "org.postgresql:postgresql", "mysql:mysql-connector-java", "activerecord", "diesel", "sqlx"}),
]


def _yaml(name: str):
    return yaml.safe_load((config.ORG_DIR / name).read_text(encoding="utf-8"))


def curated_applies(services: list[dict]) -> bool:
    known = set(_yaml("services.yaml") or {})
    found = {s["name"] for s in services}
    return len(known & found) >= max(3, len(known) // 2)


def _matches(pkg: str, signals: set[str]) -> bool:
    return pkg in signals or any(pkg.startswith(s + "/") for s in signals if "/" in s and "." in s.split("/")[0])


def infer_assets(deps: dict) -> list[dict]:
    """DataAsset rows with the services that read them and the package that says so."""
    names = {p["key"]: p["name"] for p in deps["packages"]}
    out = []
    for asset, sens, weight, desc, signals in DATA_SIGNALS:
        reads: dict[str, str] = {}
        for d in deps["depends"]:
            if d["direct"] and _matches(names.get(d["key"], ""), signals):
                reads.setdefault(d["service"], names[d["key"]])
        if reads:
            out.append({"name": asset, "sensitivity": sens, "weight": weight, "description": desc,
                        "reads": [{"service": s, "evidence": p} for s, p in sorted(reads.items())]})
    return out


def codeowners_teams(services: list[dict], root: Path) -> list[dict]:
    """Teams from CODEOWNERS: the last matching rule for a service's folder owns it (GitHub's rule order)."""
    for loc in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        f = root / loc
        if f.exists():
            break
    else:
        return []
    rules = []
    for raw in f.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            pattern, *owners = line.split()
            if owners:
                rules.append((pattern, owners))
    teams: dict[str, dict] = {}
    for s in services:
        prefix = s.get("path_prefix")
        if prefix is None:
            continue
        probe = (prefix or "") + "x"
        owners = None
        for pattern, own in rules:
            pat = pattern.lstrip("/")
            if pat in ("*", "**") or fnmatch.fnmatch(probe, pat) or fnmatch.fnmatch(probe, pat.rstrip("/") + "/*") or \
                    (pat.endswith("/") and probe.startswith(pat)) or fnmatch.fnmatch(probe, pat.rstrip("/*") + "/*"):
                owners = own
        for o in owners or []:
            slug = o.lstrip("@").lower()
            t = teams.setdefault(slug, {"slug": slug, "name": o.lstrip("@"), "owns": [], "reviewers": []})
            if "/" not in o and o.startswith("@"):
                t["reviewers"] = [o.lstrip("@")]
            if s["name"] not in t["owns"]:
                t["owns"].append(s["name"])
    return list(teams.values())


def for_repo(services: list[dict], root: Path) -> dict:
    policies = _yaml("policies.yaml")["policies"]
    if curated_applies(services):
        return {"kind": "curated", "descriptions": _yaml("services.yaml"), "teams": _yaml("teams.yaml")["teams"],
                "assets": _yaml("sensitivity.yaml")["data_assets"], "policies": policies, "incidents": _yaml("postmortems.yaml")["incidents"]}
    return {"kind": "inferred", "descriptions": {}, "teams": codeowners_teams(services, root), "assets": [], "policies": policies, "incidents": []}
