"""Saved chats (kind=ask) and PR analyses (kind=impact). Private to their author unless shared with the
project's team; a shared one is read-only for everyone but its author."""
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from warden.db.models import Conversation, Message, User  # noqa: F401 (Conversation re-exported for the API)

KINDS = ("ask", "impact")


class NotFound(LookupError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def summary(c: Conversation, owner: User | None, user_id: str) -> dict:
    return {"id": c.id, "kind": c.kind, "title": c.title, "shared": c.shared, "mine": c.user_id == user_id,
            "owner": owner.name if owner else None, "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat()}


def list_for(s: Session, user_id: str, project_id: str, kind: str = "ask", limit: int = 60) -> list[dict]:
    rows = s.execute(
        select(Conversation, User).join(User, User.id == Conversation.user_id)
        .where(Conversation.project_id == project_id, Conversation.kind == kind,
               or_(Conversation.user_id == user_id, Conversation.shared.is_(True)))
        .order_by(Conversation.updated_at.desc()).limit(limit)
    ).all()
    return [summary(c, u, user_id) for c, u in rows]


def _visible(s: Session, user_id: str, project_id: str, cid: str) -> Conversation:
    c = s.get(Conversation, cid)
    if not c or c.project_id != project_id or (c.user_id != user_id and not c.shared):
        raise NotFound("This chat doesn't exist or isn't shared with you.")
    return c


def _owned(s: Session, user_id: str, project_id: str, cid: str) -> Conversation:
    c = _visible(s, user_id, project_id, cid)
    if c.user_id != user_id:
        raise PermissionError("Only its author can change this.")
    return c


def get(s: Session, user_id: str, project_id: str, cid: str) -> dict:
    c = _visible(s, user_id, project_id, cid)
    return {**summary(c, s.get(User, c.user_id), user_id),
            "messages": [{"id": m.id, "role": m.role, "content": m.content, "data": m.data, "created_at": m.created_at.isoformat()} for m in c.messages]}


def create(s: Session, user_id: str, project_id: str, kind: str = "ask", title: str | None = None) -> Conversation:
    c = Conversation(project_id=project_id, user_id=user_id, kind=kind if kind in KINDS else "ask",
                     title=(title or "New chat").strip()[:200] or "New chat")
    s.add(c)
    s.flush()
    return c


def update(s: Session, user_id: str, project_id: str, cid: str, title: str | None = None, shared: bool | None = None) -> dict:
    c = _owned(s, user_id, project_id, cid)
    if title is not None and title.strip():
        c.title = title.strip()[:200]
    if shared is not None:
        c.shared = bool(shared)
    s.flush()
    return summary(c, s.get(User, c.user_id), user_id)


def delete(s: Session, user_id: str, project_id: str, cid: str):
    s.delete(_owned(s, user_id, project_id, cid))


def add_message(s: Session, user_id: str, project_id: str, cid: str, role: str, content: str, data: dict | None = None) -> Message:
    c = _owned(s, user_id, project_id, cid)
    m = Message(conversation_id=c.id, role=role, content=content, data=data)
    s.add(m)
    c.updated_at = _now()
    s.flush()
    return m


def history(s: Session, user_id: str, project_id: str, cid: str, limit: int = 8) -> list[dict]:
    """The last turns as LLM chat messages (answers only, no tool payloads)."""
    c = _owned(s, user_id, project_id, cid)
    return [{"role": m.role, "content": m.content} for m in c.messages if m.content][-limit:]
