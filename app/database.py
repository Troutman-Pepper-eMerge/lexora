"""Database engine + session factory. Supports SQLite (local dev) and PostgreSQL (production)."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .config import get_settings
from .models import Base

_settings = get_settings()
_url = _settings.database_url

if _url.startswith("sqlite"):
    Path(_url.split("///", 1)[-1]).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(_url, connect_args={"check_same_thread": False}, echo=False)
else:
    engine = create_engine(_url, pool_pre_ping=True, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Session:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db():
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
