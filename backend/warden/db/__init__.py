"""App database (users, teams, projects, chats): Postgres via SQLAlchemy. Neon in production."""
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from warden import config
from warden.db.models import Base

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db():
    """Creates missing tables (idempotent) and the shared demo workspace. An advisory lock keeps two processes
    starting at once (API + tests, or several workers) from racing on CREATE TABLE."""
    from warden.workspaces import ensure_demo_workspace

    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(7240611)"))
        Base.metadata.create_all(conn)
        for col, width in ("gh_owner", 80), ("gh_repo", 120), ("gh_base", 120):  # create_all never alters an existing table
            conn.execute(text(f"ALTER TABLE projects ADD COLUMN IF NOT EXISTS {col} VARCHAR({width})"))
        with Session(bind=conn) as s:
            ensure_demo_workspace(s)
            s.flush()


@contextmanager
def session() -> Session:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
