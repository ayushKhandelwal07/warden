"""Email + password accounts with server-side sessions. The browser holds only a random token in an httpOnly
cookie; the database stores its SHA-256, so a leaked table can't be replayed."""
import hashlib
import re
import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from warden import config
from warden.db.models import SessionToken, User

COOKIE = "warden_session"
_ph = PasswordHasher()
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# The signed-in user for the current request (set by the API middleware).
CURRENT_USER: ContextVar[dict | None] = ContextVar("warden_user", default=None)


class AuthError(ValueError):
    pass


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def public(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name}


def signup(s: Session, email: str, name: str, password: str) -> User:
    email = (email or "").strip().lower()
    name = (name or "").strip()[:120]
    if not _EMAIL.match(email):
        raise AuthError("Enter a valid email address.")
    if len(password or "") < 8:
        raise AuthError("Use a password of at least 8 characters.")
    if s.scalar(select(User).where(User.email == email)):
        raise AuthError("An account with this email already exists. Log in instead.")
    u = User(email=email, name=name or email.split("@")[0], password_hash=_ph.hash(password))
    s.add(u)
    s.flush()
    return u


def login(s: Session, email: str, password: str) -> User:
    u = s.scalar(select(User).where(User.email == (email or "").strip().lower()))
    try:
        if not u or not _ph.verify(u.password_hash, password or ""):
            raise VerifyMismatchError
    except VerifyMismatchError:
        raise AuthError("Wrong email or password.") from None
    return u


def start_session(s: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    s.add(SessionToken(token_hash=_hash_token(token), user_id=user.id, expires_at=_now() + timedelta(days=config.SESSION_DAYS)))
    return token


def user_for_token(s: Session, token: str | None) -> User | None:
    if not token:
        return None
    st = s.get(SessionToken, _hash_token(token))
    if not st:
        return None
    exp = st.expires_at if st.expires_at.tzinfo else st.expires_at.replace(tzinfo=timezone.utc)
    if exp < _now():
        s.delete(st)
        return None
    return s.get(User, st.user_id)


def end_session(s: Session, token: str | None):
    if token:
        s.execute(delete(SessionToken).where(SessionToken.token_hash == _hash_token(token)))


def cookie_kwargs() -> dict:
    return {"key": COOKIE, "httponly": True, "samesite": config.COOKIE_SAMESITE, "secure": config.COOKIE_SECURE,
            "max_age": config.SESSION_DAYS * 86400, "path": "/"}
