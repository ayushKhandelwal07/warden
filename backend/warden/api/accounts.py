"""Accounts, teams and the per-request project scope."""
import asyncio
from contextvars import ContextVar

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from warden import auth, config, workspaces
from warden.db import session
from warden.db.models import User

router = APIRouter(prefix="/api")

# The project the current request is scoped to (slug, id, graph, org).
CURRENT_PROJECT: ContextVar[dict | None] = ContextVar("warden_project", default=None)

# Paths that work signed out. Everything else under /api needs a session.
PUBLIC = ("/api/auth/", "/api/health", "/api/invites/", "/api/public/")


def user() -> dict:
    return auth.CURRENT_USER.get()


def project() -> dict:
    return CURRENT_PROJECT.get()


def _resolve(token: str | None, slug: str | None):
    with session() as s:
        u = auth.user_for_token(s, token)
        if not u:
            return None, None
        try:
            p = workspaces.project_json(workspaces.project_for(s, u.id, slug))
        except workspaces.AccessError as e:
            return auth.public(u), str(e)
        return auth.public(u), p


class ProjectScope:
    """Pure ASGI (so streaming responses keep the context): signed-in user + project → contextvars."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/") or scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)
        req = Request(scope)
        u, p = await asyncio.to_thread(_resolve, req.cookies.get(auth.COOKIE), req.headers.get("x-project"))
        is_public = path.startswith(PUBLIC)
        if not u and not is_public:
            return await JSONResponse(status_code=401, content={"error": "Log in to continue."})(scope, receive, send)
        if isinstance(p, str) and not is_public:
            return await JSONResponse(status_code=403, content={"error": p})(scope, receive, send)
        tokens = []
        if u:
            tokens.append((auth.CURRENT_USER, auth.CURRENT_USER.set(u)))
        if isinstance(p, dict):
            tokens.append((CURRENT_PROJECT, CURRENT_PROJECT.set(p)))
            tokens.append((config.CURRENT_GRAPH, config.CURRENT_GRAPH.set(p["graph"])))
        try:
            await self.app(scope, receive, send)
        finally:
            for var, t in reversed(tokens):
                var.reset(t)


def _err(status: int, msg: str):
    return JSONResponse(status_code=status, content={"error": msg})


def _signed_in(s, u: User) -> JSONResponse:
    token = auth.start_session(s, u)
    res = JSONResponse(workspaces.me(s, u))
    res.set_cookie(value=token, **auth.cookie_kwargs())
    return res


@router.post("/auth/signup")
def signup(body: dict = Body(default_factory=dict)):
    try:
        with session() as s:
            u = auth.signup(s, body.get("email"), body.get("name"), body.get("password"))
            workspaces.on_signup(s, u)
            if body.get("invite"):
                workspaces.accept_invite(s, u.id, str(body["invite"]))
            s.flush()
            return _signed_in(s, u)
    except (auth.AuthError, workspaces.AccessError) as e:
        return _err(400, str(e))


@router.post("/auth/login")
def login(body: dict = Body(default_factory=dict)):
    try:
        with session() as s:
            u = auth.login(s, body.get("email"), body.get("password"))
            if body.get("invite"):
                workspaces.accept_invite(s, u.id, str(body["invite"]))
            return _signed_in(s, u)
    except (auth.AuthError, workspaces.AccessError) as e:
        return _err(400, str(e))


@router.post("/auth/logout")
def logout(request: Request):
    with session() as s:
        auth.end_session(s, request.cookies.get(auth.COOKIE))
    res = JSONResponse({"ok": True})
    res.delete_cookie(auth.COOKIE, path="/")
    return res


@router.get("/auth/me")
def me():
    u = user()
    if not u:  # signed out is a normal answer here, not an error (keeps the browser console clean)
        return {"user": None, "orgs": [], "projects": []}
    with session() as s:
        return workspaces.me(s, s.get(User, u["id"]))


@router.patch("/auth/me")
def update_me(body: dict = Body(default_factory=dict)):
    u = user()
    if not u:
        return _err(401, "Not signed in.")
    with session() as s:
        row = s.get(User, u["id"])
        if (name := str(body.get("name") or "").strip()[:120]):
            row.name = name
        return workspaces.me(s, row)


# ---- teams ----

@router.get("/orgs/{org_id}/members")
def org_members(org_id: str):
    try:
        with session() as s:
            return workspaces.members(s, user()["id"], org_id)
    except workspaces.AccessError as e:
        return _err(403, str(e))


@router.post("/orgs")
def create_org(body: dict = Body(default_factory=dict)):
    from warden.db.models import Membership, Org

    name = str(body.get("name") or "").strip()[:120]
    if not name:
        return _err(400, "Give the team a name.")
    with session() as s:
        o = Org(name=name)
        s.add(o)
        s.flush()
        s.add(Membership(org_id=o.id, user_id=user()["id"], role="owner"))
        s.flush()
        return workspaces.me(s, s.get(User, user()["id"]))


@router.post("/orgs/{org_id}/invites")
def create_invite(org_id: str, body: dict = Body(default_factory=dict)):
    try:
        with session() as s:
            inv = workspaces.create_invite(s, user()["id"], org_id, str(body.get("role") or "member"))
            return {"token": inv.token, "role": inv.role, "expires_at": inv.expires_at.isoformat()}
    except workspaces.AccessError as e:
        return _err(403, str(e))


@router.patch("/orgs/{org_id}/members/{member_id}")
def set_role(org_id: str, member_id: str, body: dict = Body(default_factory=dict)):
    try:
        with session() as s:
            workspaces.set_role(s, user()["id"], org_id, member_id, str(body.get("role")))
            return workspaces.members(s, user()["id"], org_id)
    except (workspaces.AccessError, ValueError) as e:
        return _err(403, str(e))


@router.delete("/orgs/{org_id}/members/{member_id}")
def remove_member(org_id: str, member_id: str):
    try:
        with session() as s:
            workspaces.remove_member(s, user()["id"], org_id, member_id)
        return {"ok": True}
    except workspaces.AccessError as e:
        return _err(403, str(e))


@router.get("/invites/{token}")
def invite_info(token: str):
    try:
        with session() as s:
            return workspaces.invite_info(s, token)
    except workspaces.AccessError as e:
        return _err(404, str(e))


@router.post("/invites/{token}/accept")
def accept_invite(token: str):
    if not user():
        return _err(401, "Log in to accept the invite.")
    try:
        with session() as s:
            info = workspaces.accept_invite(s, user()["id"], token)
            return {**info, **workspaces.me(s, s.get(User, user()["id"]))}
    except workspaces.AccessError as e:
        return _err(400, str(e))



# ---- projects ----

@router.post("/projects")
def create_project(body: dict = Body(default_factory=dict)):
    try:
        with session() as s:
            p = workspaces.create_project(s, user()["id"], str(body.get("org_id") or ""), str(body.get("name") or ""))
            s.flush()
            return {"project": workspaces.project_json(p), **workspaces.me(s, s.get(User, user()["id"]))}
    except workspaces.AccessError as e:
        return _err(403, str(e))
    except ValueError as e:
        return _err(400, str(e))


@router.delete("/projects/{project_id}")
def delete_project(project_id: str):
    try:
        with session() as s:
            workspaces.delete_project(s, user()["id"], project_id)
            s.flush()
            return workspaces.me(s, s.get(User, user()["id"]))
    except workspaces.AccessError as e:
        return _err(403, str(e))
