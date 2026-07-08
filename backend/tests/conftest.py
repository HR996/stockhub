"""Shared pytest fixtures — DB session per test with truncate teardown; session-wide baostock login."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://istock:istock@localhost:5432/istock",
)


@pytest.fixture(scope="session")
def engine():
    return create_engine(TEST_DATABASE_URL, future=True)


@pytest.fixture(scope="session")
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@pytest.fixture()
def db(session_factory) -> Iterator[Session]:
    """Yield a session; truncate tables the test touched afterward."""
    session: Session = session_factory()
    _truncate_test_tables(session)
    try:
        yield session
        session.commit()
    finally:
        session.rollback()
        _truncate_test_tables(session)
        session.close()


def _truncate_test_tables(session: Session) -> None:
    with session.begin():
        session.execute(
            text(
                "TRUNCATE TABLE stock_basic, trade_calendar, k_line_daily, "
                "data_update_task, latest_market_cap, stock_adj_factor, sw_industry_classify, "
                "sw_industry_member, browse_history, factor_config, "
                "factor_result, factor_result_row, factor_result_stock "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture(scope="session")
def bs_session() -> Iterator[None]:
    """Session-wide baostock login — one login per pytest process to avoid rate-limiting.

    baostock's anonymous endpoint blacklists IPs that login too often (`error_code=10001011:
    黑名单用户`). Sharing one login across every integration test keeps us well under the limit.
    On persistent blacklist, tests that depend on this fixture are **skipped**, not errored.
    """
    from app.adapters.baostock_adapter import baostock_session
    from app.core.errors import AdapterAuthError, AdapterConnectionError

    try:
        with baostock_session():
            yield
    except (AdapterAuthError, AdapterConnectionError) as exc:
        pytest.skip(f"baostock unavailable in this environment: {exc}")
