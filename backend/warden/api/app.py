"""HTTP API for the Warden UI.

    uvicorn warden.api.app:app --port 8000 --app-dir backend
"""
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from warden import config
from warden.graph import overview

app = FastAPI(title="Warden API")

BROWSER_URL = os.getenv("FALKORDB_BROWSER_URL", "http://localhost:3000")


@app.get("/api/health")
def health():
    try:
        h = overview.health()
    except Exception as e:  # FalkorDB down or graph missing: the UI shows it instead of a blank page
        return JSONResponse(status_code=503, content={"status": "down", "graph": config.org_graph_name(), "error": str(e)[:200]})
    return {"status": "ok", "graph": config.org_graph_name(), "browser_url": BROWSER_URL, **h}


@app.get("/api/overview")
def get_overview():
    try:
        return {"totals": overview.totals(), "hero": overview.kev_hero()}
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)[:200]})


class SPAStaticFiles(StaticFiles):
    """Serves the built UI; unknown paths (client-side routes like /approvals) fall back to index.html."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404 and not path.startswith("api"):
                return await super().get_response("index.html", scope)
            raise


# Production: serve the built UI from the same origin (one deploy).
_dist = config.ROOT_DIR / "frontend" / "dist"
if _dist.exists():
    app.mount("/", SPAStaticFiles(directory=_dist, html=True), name="ui")
