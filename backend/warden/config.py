import os
from contextvars import ContextVar
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
load_dotenv(ROOT_DIR / ".env")

FALKORDB_HOST = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", "6380"))
FALKORDB_USERNAME = os.getenv("FALKORDB_USERNAME") or None
FALKORDB_PASSWORD = os.getenv("FALKORDB_PASSWORD") or None
FALKORDB_SSL = os.getenv("FALKORDB_SSL", "").lower() in ("1", "true", "yes")  # FalkorDB Cloud endpoints use TLS
TENANT = os.getenv("TENANT", "demo")

DEMO_REPO_URL = os.getenv("DEMO_REPO_URL", "https://github.com/GoogleCloudPlatform/microservices-demo.git")
DEMO_REF = os.getenv("DEMO_REF", "v0.8.0")
# What the project page shows as its repository: our fork when one is configured, else the source repo.
PROJECT_REPO_URL = (f"https://github.com/{os.getenv('GITHUB_OWNER')}/{os.getenv('GITHUB_REPO', 'microservices-demo')}" if os.getenv("GITHUB_OWNER") else DEMO_REPO_URL)
HISTORY_SINCE = os.getenv("HISTORY_SINCE", "2022-06-15")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY") or None
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

# Where the Warden UI is served; PR comments and PR bodies link back to it.
WARDEN_URL = os.getenv("WARDEN_URL", "http://localhost:5173").rstrip("/")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or None
GITHUB_OWNER = os.getenv("GITHUB_OWNER") or None
GITHUB_REPO = os.getenv("GITHUB_REPO", "microservices-demo")
# Branch Warden opens PRs against (the fork branch pinned to DEMO_REF); empty = the fork's default branch.
GITHUB_BASE = os.getenv("GITHUB_BASE", "demo-base") or None

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://warden:warden@localhost:5433/warden")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-only-secret-change-me")
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").lower()
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "14"))

# Browser origins allowed to call the API (the Vercel frontend), comma-separated.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5175").split(",") if o.strip()]

DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
REPO_DIR = RAW_DIR / "repo"
CACHE_DIR = RAW_DIR / "cache"
ORG_DIR = BACKEND_DIR / "org"

# Upstream URL used for links in evidence (PRs, files). Never written to.
UPSTREAM_WEB = "https://github.com/GoogleCloudPlatform/microservices-demo"


# The project graph for the current request. Set by the API middleware from the signed-in user's project, so every
# graph call underneath (tools, planner, sync, watcher, agent) is scoped without passing it through each function.
CURRENT_GRAPH: ContextVar[str | None] = ContextVar("warden_graph", default=None)


def org_graph_name(tenant: str = TENANT) -> str:
    return CURRENT_GRAPH.get() or f"org_{tenant}"


def golden_graph_name(tenant: str = TENANT) -> str:
    return f"{org_graph_name(tenant)}_golden"
