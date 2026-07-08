import { apiDelete, apiGet, apiPost } from "@/api/http";

export interface BrowseField {
  key: string;
  title: string;
  data_type: string;
  description: string;
  sortable: boolean;
  filterable: boolean;
}

export interface BrowseTableSpec {
  key: string;
  title: string;
  description: string;
  fields: BrowseField[];
}

export interface BrowseFilter {
  field: string;
  op: "eq" | "contains" | "gte" | "lte" | "is_null";
  value?: string | number | boolean | null;
}

export interface BrowseQuery {
  page: number;
  page_size: number;
  order_by?: string;
  order?: "asc" | "desc";
  fields?: string[];
  filters?: BrowseFilter[];
}

export interface BrowseQueryResult {
  items: Record<string, unknown>[];
  total: number;
  page: number;
  page_size: number;
  fields: string[];
}

export interface BrowseHistoryItem {
  id: number;
  username: string;
  page_key: string;
  page_title: string;
  page_state: Record<string, unknown>;
  visited_at: string;
}

export function getBrowseTables(): Promise<{ items: BrowseTableSpec[] }> {
  return apiGet("/api/browse/tables");
}

export function queryBrowseTable(tableKey: string, query: BrowseQuery): Promise<BrowseQueryResult> {
  return apiPost(`/api/browse/tables/${tableKey}/query`, query);
}

export function getBrowseHistory(): Promise<{ items: BrowseHistoryItem[] }> {
  return apiGet("/api/browse/history");
}

export function saveBrowseHistory(body: {
  page_key: string;
  page_title: string;
  page_state: Record<string, unknown>;
}): Promise<BrowseHistoryItem> {
  return apiPost("/api/browse/history", body);
}

export function deleteBrowseHistory(id: number): Promise<{ deleted: boolean }> {
  return apiDelete(`/api/browse/history/${id}`);
}

export function clearBrowseHistory(): Promise<{ deleted: number }> {
  return apiDelete("/api/browse/history");
}
