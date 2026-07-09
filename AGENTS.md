# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

**istock** — A-share quantitative analysis web system for a small number of users. Single-machine, low-concurrency. Goal: data foundation + data health + data browsing + stock detail + Shenwan industry classification maintenance + sector momentum factor.

Stack: FastAPI + SQLAlchemy 2.x + PostgreSQL 15 (backend), React 18 + Vite 5 + AntD 5 (frontend). Data sourced from **baostock** (K-line, stock basics, trade calendar), **akshare** (market cap fallback), and **Tushare Pro** (申万 SW2021 industry classification).

## Commands

### Backend (run from `backend/`)

```bash
uv sync --group dev                          # install deps
uv run uvicorn app.main:app --reload --port 8000  # start dev server
uv run pytest                                # all tests
uv run pytest -m "not integration"          # unit tests only (no external deps)
uv run pytest -m integration                # integration tests (need real DB)
uv run pytest tests/unit/test_health_api.py # single test file
uv run ruff check app/ tests/               # lint
uv run ruff check --fix app/ tests/         # lint + autofix
uv run mypy app/                            # type check
uv run alembic upgrade head                 # apply DB migrations
```

Environment variable required for local dev:
```bash
export DATABASE_URL=postgresql+psycopg://istock:istock@localhost:5432/istock
```

### Frontend (run from `frontend/`)

```bash
npm install
npm run dev          # Vite dev server on :5173
npm run build        # production build
npm run typecheck    # tsc --noEmit
npm run lint         # eslint
```

Vite proxies `/api` to `VITE_API_TARGET` (defaults to `http://localhost:8000`).

PostgreSQL runs as a native system service or on a separate database host. Local DB connection:
`postgresql+psycopg://istock:istock@localhost:5432/istock`.

## Architecture

### Backend layers (strict one-direction dependency)

```
API (app/api/)          — HTTP only: param validation, envelope wrapping, error mapping
  └─ Service (app/services/)  — orchestration, transaction boundary, audit logging
       ├─ Repository (app/repositories/)  — domain-method CRUD, upserts; no raw SQL in callers
       ├─ Adapter (app/adapters/)         — external sources only (baostock, akshare, tushare); never writes DB
       └─ Factor (app/factors/)           — read-only via Repository; never calls Adapter or DB directly
```

**Forbidden cross-layer calls**: Repository → Service/Adapter, Adapter → Repository, Factor → Adapter/DB, API → Repository.

### API response envelope

All endpoints return `{success: bool, data: any, message: str}` — **never** throw HTTP 4xx/5xx for business errors. Use helpers from `app/core/envelope.py`:

```python
return ok(data)                              # success
return JSONResponse(content=fail("CODE", "msg", detail={}))  # failure
```

Error code prefixes: `AUTH_*`, `VALIDATION_*`, `NOT_FOUND_*`, `CONFLICT_*`, `ADAPTER_*`, `INTERNAL_*`.

### Key infrastructure (`app/core/`)

- `config.py` — `Settings` dataclass loaded from env vars; `settings` singleton
- `db.py` — SQLAlchemy engine, `session_scope()` context manager
- `deps.py` — FastAPI dependencies: `get_db` (DB session), `get_current_user` (reads `X-User` header, currently a stub — no real auth)
- `envelope.py` — `ok()` / `fail()` helpers
- `errors.py` — domain exceptions: `NotFoundError`, `ValidationError`, `AdapterError` and subclasses

### Auth (v1 stub)

Auth is not enforced. The frontend stores the chosen username in `localStorage` via Zustand `authStore` and injects it as `X-User` header on every request. The backend reads it via `get_current_user` dep and returns `"anonymous"` if absent. **No password check for regular login**; admin password is checked separately via `X-Admin-Password` header.

### Frontend data flow

```
Pages → Components → API client (src/api/*.ts)
                   → Zustand store (src/store/)
API client uses axios + interceptors (src/api/http.ts):
  - auto-inject X-User from authStore
  - unwrap {success, data, message}: success=true → return data.data; success=false → throw EnvelopeError
```

Type definitions in `src/api/*.ts` are hand-aligned with backend Pydantic schemas (no codegen).

### Database schema highlights

- All PKs are `BIGSERIAL`; business keys are `UNIQUE` indexes.
- All timestamps are `TIMESTAMPTZ`; stored in UTC, displayed in `Asia/Shanghai`.
- `k_line_daily` stores raw facts only; factors dynamically combine raw closes with `stock_adj_factor`. `k_line_qfq_latest` is a rebuildable display cache.
- `factor_result` (1) → `factor_result_row` (N levels: L1/L2/L3) + `factor_result_stock` (M stocks) — all CASCADE-deleted together.
- `sw_industry_classify` + `sw_industry_member` hold a single **current snapshot** of SW2021 分类 refreshed by the weekly Tushare sync (TRUNCATE + INSERT semantics; no version table, no rollback).
- Schema changes must go through Alembic only — never hand-edit the DB.

### File size constraint

**Hard limit: 500 lines per source file.** Pre-planned split module: `app/factors/` (6 sub-files). Any other file approaching 400 lines should be split proactively.

## Development Notes

- **Tests**: unit tests (`tests/unit/`) use no external deps. Integration tests (`tests/integration/`) need a real PostgreSQL instance and are tagged `@pytest.mark.integration`.
- **Migrations**: `alembic/versions/` — only add new revision files, never edit existing ones.
- **baostock quota**: 50k calls/day cap. `AdapterQuotaExceededError` is raised on `error_code=10001007`; callers must abort the batch (no retry).
- **Tushare quota**: tier-gated at 2000 points for SW endpoints (`index_classify`, `index_member_all`). Adapter maps `权限`/`积分`/`频率` error messages to `AdapterAuthError` / `AdapterQuotaExceededError` respectively; rate-limited calls back off 60s then abort.
- **upsert pattern**: all `Repository.upsert_many()` use `core/db.py::chunked` in batches to stay under PostgreSQL's 65535-parameter limit per statement.
- **Scheduler**: APScheduler runs two independent jobs — daily K-line/stock_basic/trade_cal/market_cap (`SCHEDULER_ENABLED=true`, default off) and weekly SW industry sync from Tushare (`SCHEDULER_SW_ENABLED=true`, default off; cron defaults to Sat 02:07 Asia/Shanghai). SW sync requires `TUSHARE_TOKEN` env var.
- **申万 (Shenwan) classification** comes from Tushare Pro `pro.index_classify(src='SW2021')` + `pro.index_member_all(is_new='Y')`. See `app/adapters/tushare_adapter.py` and `app/services/sw_sync_service.py`. Read-only endpoints live at `/api/industry/*`.
