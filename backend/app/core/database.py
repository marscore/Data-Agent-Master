"""SQLAlchemy engine + session. SQLite by default (self-contained), Postgres
via DATABASE_URL. Holds platform config (agents), trace runs/spans, and the
human-readable conversation log."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import resolve_data_path, settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = settings.DATABASE_URL
    connect_args = {}
    if url.startswith("sqlite"):
        path = url.split("///")[-1]
        if path and path != ":memory:":
            abs_path = resolve_data_path(path)
            os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
            url = f"sqlite:///{abs_path}"
        connect_args = {"check_same_thread": False}
    return create_engine(url, echo=False, future=True, pool_pre_ping=True, connect_args=connect_args)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def init_db() -> None:
    from app.platform import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
    logger.info("DB initialized: %s", settings.DATABASE_URL)


@contextmanager
def session_scope() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
