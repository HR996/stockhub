"""browse_history — saved page states for data browsing."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BrowseHistory(Base):
    __tablename__ = "browse_history"
    __table_args__ = (
        Index("ix_browse_history_user_visited", "username", "visited_at"),
        Index("ix_browse_history_user_key_visited", "username", "page_key", "visited_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    page_key: Mapped[str] = mapped_column(String(64), nullable=False)
    page_title: Mapped[str] = mapped_column(String(255), nullable=False)
    page_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    visited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
