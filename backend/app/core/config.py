"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "istock"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+psycopg://istock:istock@postgres:5432/istock"
    preconfigured_users: tuple[str, ...] = ("admin",)
    admin_password_hash: str = ""
    scheduler_enabled: bool = False
    scheduler_hour: int = 2
    scheduler_minute: int = 30
    scheduler_triggered_by: str = "scheduler"
    tushare_token: str | None = None
    scheduler_sw_enabled: bool = False
    scheduler_sw_day_of_week: str = "sat"
    scheduler_sw_hour: int = 2
    scheduler_sw_minute: int = 7

    @classmethod
    def load(cls) -> Settings:
        users = os.getenv("PRECONFIGURED_USERS", "admin")
        token = os.getenv("TUSHARE_TOKEN") or None
        return cls(
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            preconfigured_users=tuple(u.strip() for u in users.split(",") if u.strip()),
            admin_password_hash=os.getenv("ADMIN_PASSWORD_HASH", ""),
            scheduler_enabled=os.getenv("SCHEDULER_ENABLED", "false").lower() == "true",
            scheduler_hour=int(os.getenv("SCHEDULER_HOUR", "2")),
            scheduler_minute=int(os.getenv("SCHEDULER_MINUTE", "30")),
            scheduler_triggered_by=os.getenv("SCHEDULER_TRIGGERED_BY", "scheduler"),
            tushare_token=token,
            scheduler_sw_enabled=os.getenv("SCHEDULER_SW_ENABLED", "false").lower() == "true",
            scheduler_sw_day_of_week=os.getenv("SCHEDULER_SW_DAY_OF_WEEK", "sat"),
            scheduler_sw_hour=int(os.getenv("SCHEDULER_SW_HOUR", "2")),
            scheduler_sw_minute=int(os.getenv("SCHEDULER_SW_MINUTE", "7")),
        )


settings = Settings.load()
