/**
 * Health API client — wraps the backend `/api/health/*` endpoints.
 */
import { apiGet } from "@/api/http";

export interface TableSummary {
  count: number;
  last_updated: string | null;
}

export interface HealthSummary {
  stock_basic: TableSummary;
  trade_calendar: TableSummary;
  k_line_daily: TableSummary;
  latest_market_cap: TableSummary;
  latest_task: TableSummary;
}

export interface DayStatus {
  date: string;
  is_open: boolean;
  status: "green" | "yellow" | "red" | "gray";
  expected: number;
  actual: number;
  has_anomaly: boolean;
}

export interface CalendarMonth {
  year: number;
  month: number;
  days: DayStatus[];
}

export interface DayDetail {
  date: string;
  expected_count: number;
  success_count: number;
  missing_count: number;
  error_count: number;
  missing_ts_codes: string[];
  error_ts_codes: string[];
  latest_task: {
    status: string | null;
    finished_at: string | null;
    error_summary: Record<string, unknown> | null;
  } | null;
}

export interface TaskRow {
  id: number;
  task_type: string;
  task_key: string | null;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  expected_count: number | null;
  success_count: number | null;
  missing_count: number | null;
  error_count: number | null;
  error_summary: Record<string, unknown> | null;
  created_by: string;
}

export interface PagedResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export function getSummary(): Promise<HealthSummary> {
  return apiGet<HealthSummary>("/api/health/summary");
}

export function getCalendar(year: number, month: number): Promise<CalendarMonth> {
  return apiGet<CalendarMonth>("/api/health/kline/calendar", { year, month });
}

export function getDayDetail(date: string): Promise<DayDetail> {
  return apiGet<DayDetail>(`/api/health/kline/day/${date}`);
}

export function getTasks(
  page = 1,
  pageSize = 50,
  orderBy: "started_at" | "finished_at" | "task_type" | "status" = "started_at",
  order: "asc" | "desc" = "desc",
): Promise<PagedResult<TaskRow>> {
  return apiGet<PagedResult<TaskRow>>("/api/health/tasks", {
    page,
    page_size: pageSize,
    order_by: orderBy,
    order,
  });
}
