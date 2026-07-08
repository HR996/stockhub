/**
 * Industry API client — wraps /api/industry/* endpoints.
 *
 * Types mirror the backend Pydantic-ish shape (dataclasses in app/services/sw_query_service.py).
 */
import { apiGet } from "@/api/http";

export interface IndustryL3Node {
  index_code: string;
  industry_code: string;
  industry_name: string;
  stock_count: number;
}

export interface IndustryL2Node {
  index_code: string;
  industry_code: string;
  industry_name: string;
  children: IndustryL3Node[];
}

export interface IndustryL1Node {
  index_code: string;
  industry_code: string;
  industry_name: string;
  children: IndustryL2Node[];
}

export interface IndustryTree {
  src: string;
  levels: IndustryL1Node[];
}

export interface StockIndustry {
  ts_code: string;
  l1_index_code: string;
  l1_name: string;
  l2_index_code: string;
  l2_name: string;
  l3_index_code: string;
  l3_name: string;
  in_date: string | null;
  out_date: string | null;
}

export interface LastSyncInfo {
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  classify_expected: number | null;
  classify_success: number | null;
  orphan_count: number | null;
  error_message: string | null;
}

export type IndustryLevel = "L1" | "L2" | "L3";

export interface NodeStockRow {
  ts_code: string;
  name: string | null;
  l1_index_code: string;
  l1_name: string;
  l2_index_code: string;
  l2_name: string;
  l3_index_code: string;
  l3_name: string;
  in_date: string | null;
}

export interface NodeStockList {
  level: IndustryLevel;
  index_code: string;
  industry_name: string;
  total: number;
  stocks: NodeStockRow[];
}

export function getIndustryTree(): Promise<IndustryTree> {
  return apiGet<IndustryTree>("/api/industry/tree");
}

export function getStockIndustry(tsCode: string): Promise<StockIndustry> {
  return apiGet<StockIndustry>(`/api/industry/stock/${tsCode}`);
}

export function getLastSyncInfo(): Promise<LastSyncInfo> {
  return apiGet<LastSyncInfo>("/api/industry/last-sync");
}

export function getNodeStocks(level: IndustryLevel, indexCode: string): Promise<NodeStockList> {
  return apiGet<NodeStockList>(`/api/industry/node/${level}/${indexCode}/stocks`);
}
