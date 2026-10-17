"""Teams (orgs), members, invites and projects. Every project points at one FalkorDB graph; membership in the
project's org is what lets a user query that graph."""
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from warden import config
from warden.db.models import Invite, Membership, Org, Project, User

DEMO_ORG_ID = "demo"
DEMO_PROJECT_SLUG = "online-boutique"


class AccessError(PermissionError):
    pass


def ensure_demo_workspace(s: Session):
    """The shared demo team, bound to the already-ingested org graph. Every new user joins it."""
    if not s.get(Org, DEMO_ORG_ID):
        s.add(Org(id=DEMO_ORG_ID, name="Online Boutique (demo)"))
        s.flush()
    if not s.scalar(select(Project).where(Project.slug == DEMO_PROJECT_SLUG)):
        s.add(Project(org_id=DEMO_ORG_ID, slug=DEMO_PROJECT_SLUG, name="Online Boutique", graph=f"org_{config.TENANT}",
                      repo_url=config.DEMO_REPO_URL, ref=config.DEMO_REF))


def on_signup(s: Session, user: User):
    """A personal team (owner) plus membership in the shared demo team."""
    personal = Org(name=f"{user.name}'s team", personal=True)
    s.add(personal)
    s.flush()
    s.add(Membership(org_id=personal.id, user_id=user.id, role="owner"))
    ensure_demo_workspace(s)
    s.add(Membership(org_id=DEMO_ORG_ID, user_id=user.id, role="member"))


def role_in(s: Session, user_id: str, org_id: str) -> str | None:
    m = s.scalar(select(Membership).where(Membership.org_id == org_id, Membership.user_id == user_id))
    return m.role if m else None


def projects_for(s: Session, user_id: str) -> list[Project]:
    return list(s.scalars(
        select(Project).join(Membership, Membership.org_id == Project.org_id)
        .where(Membership.user_id == user_id).order_by(Project.created_at)
    ))


def project_for(s: Session, user_id: str, slug: str | None) -> Project:
    """The project the request is about. No slug: the user's first project (the demo)."""
    ps = projects_for(s, user_id)
    if not ps:
        raise AccessError("You have no projects yet.")
    if not slug:
        return next((p for p in ps if p.slug == DEMO_PROJECT_SLUG), ps[0])
    p = next((p for p in ps if p.slug == slug), None)
    if not p:
        raise AccessError("You don't have access to this project.")
    return p


def project_json(p: Project) -> dict:
    return {"id": p.id, "slug": p.slug, "name": p.name, "org_id": p.org_id, "org_name": p.org.name, "graph": p.graph,
            "repo_url": p.repo_url, "ref": p.ref, "status": p.status, "status_detail": p.status_detail}


def me(s: Session, user: User) -> dict:
    orgs = s.execute(select(Org, Membership.role).join(Membership).where(Membership.user_id == user.id).order_by(Org.personal.desc(), Org.created_at)).all()
    return {
        "user": {"id": user.id, "email": user.email, "name": user.name},
        "orgs": [{"id": o.id, "name": o.name, "personal": o.personal, "role": r} for o, r in orgs],
        "projects": [project_json(p) for p in projects_for(s, user.id)],
    }


# ---- team management ----

def _require_admin(s: Session, user_id: str, org_id: str):
    if role_in(s, user_id, org_id) not in ("owner", "admin"):
        raise AccessError("Only a team owner or admin can do this.")


def members(s: Session, user_id: str, org_id: str) -> list[dict]:
    if not role_in(s, user_id, org_id):
        raise AccessError("You're not in this team.")
    rows = s.execute(select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.org_id == org_id).order_by(Membership.created_at)).all()
    return [{"user_id": u.id, "name": u.name, "email": u.email, "role": m.role, "joined_at": m.created_at.isoformat()} for m, u in rows]


def create_invite(s: Session, user_id: str, org_id: str, role: str = "member") -> Invite:
    _require_admin(s, user_id, org_id)
    if role not in ("member", "admin"):
        role = "member"
    inv = Invite(token=secrets.token_urlsafe(24), org_id=org_id, role=role, created_by=user_id,
                 expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    s.add(inv)
    return inv


def invite_info(s: Session, token: str) -> dict:
    inv = s.get(Invite, token)
    if not inv or inv.used_by:
        raise AccessError("This invite link is invalid or was already used.")
    exp = inv.expires_at if inv.expires_at.tzinfo else inv.expires_at.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise AccessError("This invite link has expired. Ask for a new one.")
    org = s.get(Org, inv.org_id)
    inviter = s.get(User, inv.created_by)
    return {"org_id": org.id, "org_name": org.name, "role": inv.role, "invited_by": inviter.name if inviter else None}


def accept_invite(s: Session, user_id: str, token: str) -> dict:
    info = invite_info(s, token)
    inv = s.get(Invite, token)
    if not role_in(s, user_id, inv.org_id):
        s.add(Membership(org_id=inv.org_id, user_id=user_id, role=inv.role))
    inv.used_by = user_id
    return info


def set_role(s: Session, user_id: str, org_id: str, member_id: str, role: str):
    _require_admin(s, user_id, org_id)
    m = s.scalar(select(Membership).where(Membership.org_id == org_id, Membership.user_id == member_id))
    if not m or m.role == "owner":
        raise AccessError("You can't change the owner's role.")
    if role not in ("member", "admin"):
        raise ValueError("Role must be member or admin.")
    m.role = role


def remove_member(s: Session, user_id: str, org_id: str, member_id: str):
    if member_id != user_id:
        _require_admin(s, user_id, org_id)
    m = s.scalar(select(Membership).where(Membership.org_id == org_id, Membership.user_id == member_id))
    if not m:
        return
    if m.role == "owner":
        raise AccessError("The owner can't leave or be removed.")
    s.delete(m)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "project"


# ---- projects ----

def create_project(s: Session, user_id: str, org_id: str, name: str) -> Project:
    """A new project gets its own FalkorDB graph: a private copy of the sample org, so the team can sync,
    rehearse fixes and record decisions without touching anyone else's graph."""
    from warden.graph.client import copy_graph, graph_exists

    _require_admin(s, user_id, org_id)
    name = (name or "").strip()[:120]
    if not name:
        raise ValueError("Give the project a name.")
    base = slugify(name)
    slug, n = base, 2
    while s.scalar(select(Project).where(Project.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    p = Project(org_id=org_id, slug=slug, name=name, graph="", repo_url=config.DEMO_REPO_URL, ref=config.DEMO_REF, status="ready")
    s.add(p)
    s.flush()
    p.graph = f"proj_{p.id}"
    src = f"org_{config.TENANT}_golden" if graph_exists(f"org_{config.TENANT}_golden") else f"org_{config.TENANT}"
    copy_graph(src, p.graph)
    copy_graph(src, f"{p.graph}_golden")  # what "Reset" restores for this project
    return p


def delete_project(s: Session, user_id: str, project_id: str):
    from warden.graph.client import delete_graph, graph_exists

    p = s.get(Project, project_id)
    if not p:
        raise AccessError("No such project.")
    _require_admin(s, user_id, p.org_id)
    if p.slug == DEMO_PROJECT_SLUG:
        raise AccessError("The shared demo project can't be deleted.")
    for g in (p.graph, f"{p.graph}_golden", f"{p.graph}_prev", f"agents_{p.graph}"):
        if graph_exists(g):
            delete_graph(g)
    s.delete(p)
