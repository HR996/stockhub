"""SQLAlchemy engine + Session + Base declarative class."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, mapped_column, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    type_annotation_map: ClassVar[dict] = {
        datetime: DateTime(timezone=True),
    }


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session context — commits on success, rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a transactional session."""
    with session_scope() as session:
        yield session


def mapped_col_created_at() -> object:
    """Reusable column definition helper for created_at fields (server default now)."""
    from sqlalchemy import func

    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def mapped_col_updated_at() -> object:
    """Reusable column definition helper for updated_at fields (auto-refresh)."""
    from sqlalchemy import func

    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# PostgreSQL wire protocol caps bound parameters at 65535 (uint16). Repository
# helpers chunk large upserts to stay well under that ceiling regardless of column count.
_PG_PARAM_LIMIT = 60_000


def chunked(items: list, columns_per_row: int) -> Iterator[list]:
    """Yield sub-lists small enough that `columns_per_row * len(chunk)` stays <60k params."""
    if not items:
        return
    max_rows = max(1, _PG_PARAM_LIMIT // max(columns_per_row, 1))
    for i in range(0, len(items), max_rows):
        yield items[i : i + max_rows]
