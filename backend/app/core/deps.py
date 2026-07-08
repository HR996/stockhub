"""FastAPI dependencies (auth stubs + DB session).

`get_current_user` is a **stub** — it reads `X-User` and returns it as-is without
verification. Real validation against the preconfigured user list is P2-05.
Kept here so all API endpoints can already declare the dependency and swap in the
strict version transparently later.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Header
from sqlalchemy.orm import Session

from app.core.db import session_scope


def get_current_user(x_user: str | None = Header(default=None)) -> str:
    """Return the caller's username from `X-User` (or 'anonymous' if absent).

    v1 stub: no validation. Do not depend on this for authorization decisions.
    """
    return x_user or "anonymous"


def get_db() -> Iterator[Session]:
    """Yield a transactional DB session."""
    with session_scope() as session:
        yield session
