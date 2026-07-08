# Tushare Pro — 申万 (Shenwan) industry data

> ⚠️ This file replaces the old **sw_parser cheatsheet** (v0). The old flow (manager
> uploads a zip/rar/xls package → `sw_parser/` decomposes it → versioned table set
> with `is_current` flip) is **retired**. All Shenwan data now comes from Tushare
> Pro via `app/adapters/tushare_adapter.py`.

## Endpoints we use

| Purpose | Tushare method | Notes |
|---|---|---|
| L1/L2/L3 catalog | `pro.index_classify(level='L1'|'L2'|'L3', src='SW2021')` | One call per level. Returns `index_code`, `industry_code`, `industry_name`, `parent_code`, `is_pub`. |
| Stock ↔ industry membership | `pro.index_member_all(is_new='Y')` (fallback: per-L3 `pro.index_member`) | Only current members. |

## Key semantics

- **`index_code`** = 交易所指数码 (e.g. `801010.SI`). Used as tree node key and in `sw_industry_member.l{1,2,3}_index_code`.
- **`industry_code`** = 业务码; every classify row has one, and it is the reference target of children's `parent_code`. L2 rows' `parent_code` points to an L1 row's `industry_code`; L3 rows' `parent_code` points to an L2 row's `industry_code`.
- **Version**: we always pass `src='SW2021'` — the current standard (31 L1 / 134 L2 / 346 L3).
- **Snapshot only**: each sync is `TRUNCATE + INSERT`; no `sw_industry_version` table, no rollback.

## Auth / quotas

- Token: `TUSHARE_TOKEN` env var → `tushare.set_token(...)` → `tushare.pro_api()`.
- 2000-point tier: 200 req/min soft cap. Adapter enforces ~0.35 s min interval.
- Error mapping (`_map_tushare_error`):
  - `权限` / `未开通` / `无权` / `token` → `AdapterAuthError`
  - `积分` / `点数` → `AdapterQuotaExceededError`
  - `频率` / `每分钟` → back off 60 s, one retry, then `AdapterQuotaExceededError`
  - anything else → `AdapterDataError`

## Callsites

- Adapter: `backend/app/adapters/tushare_adapter.py` (`fetch_sw_classify`, `fetch_sw_members`, `tushare_session`)
- Types: `backend/app/adapters/tushare_types.py` (`SWClassifyRow`, `SWMemberRow`)
- Service: `backend/app/services/sw_sync_service.py` (`sync_sw_industry`)
- Query: `backend/app/services/sw_query_service.py` (`get_industry_tree`, `get_stock_industry`, `get_last_sync_info`)
- Scheduler: `backend/app/services/scheduler.py` (`run_weekly_sw_sync`, job id `sw_weekly_sync`)
- API: `backend/app/api/industry.py`
