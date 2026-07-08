import { apiDelete, apiGet, apiPatch, apiPost } from "@/api/http";

export type FactorLevel = "L1" | "L2" | "L3";

export interface FactorParams {
  basedate: string;
  window: number;
  top_ratio: number;
  classification: "SW";
  level: FactorLevel;
  return_method: "simple" | "log";
  score_method: "median_return_score" | "top_count_score";
}

export interface FactorResultHead {
  id: number;
  params: FactorParams;
  basedate: string;
  start_date: string;
  classification: string;
  industry_snapshot_at: string | null;
  stale: boolean;
  stale_reason: string | null;
  created_at: string;
  created_by: string;
}

export interface FactorRow {
  id: number;
  result_id: number;
  level: FactorLevel;
  sector_code: string;
  sector_name: string;
  parent_sector_code: string | null;
  sector_stock_count: number;
  sector_top_stock_count: number;
  top_density: number;
  median_return: number | null;
  momentum_score: number;
  small_sample_flag: boolean;
}

export interface FactorStockRow {
  ts_code: string;
  stock_name: string;
  stock_return: number | null;
  is_top: boolean;
  missing_reason: string | null;
}

export interface FactorConfig {
  id: number;
  name: string;
  params: FactorParams;
  updated_at: string;
}

export function calculateFactor(params: FactorParams): Promise<{ result: FactorResultHead; level: FactorLevel; rows: FactorRow[] }> {
  return apiPost("/api/factor/results", params);
}

export function getFactorResult(id: number, level?: FactorLevel): Promise<{ result: FactorResultHead; level: FactorLevel; rows: FactorRow[] }> {
  return apiGet(`/api/factor/results/${id}`, level ? { level } : undefined);
}

export function getFactorResults(): Promise<{ items: FactorResultHead[] }> {
  return apiGet("/api/factor/results");
}

export function getFactorChildren(id: number, parent_level: FactorLevel, parent_sector_code: string): Promise<{ level: FactorLevel; rows: FactorRow[] }> {
  return apiGet(`/api/factor/results/${id}/children`, { parent_level, parent_sector_code });
}

export function getFactorSectorStocks(id: number, level: FactorLevel, sectorCode: string): Promise<{ stocks: FactorStockRow[] }> {
  return apiGet(`/api/factor/results/${id}/sectors/${level}/${sectorCode}/stocks`);
}

export function recalculateFactor(id: number): Promise<{ result: FactorResultHead; level: FactorLevel; rows: FactorRow[] }> {
  return apiPost(`/api/factor/results/${id}/recalculate`);
}

export function getFactorConfigs(): Promise<{ items: FactorConfig[] }> {
  return apiGet("/api/factor/configs");
}

export function createFactorConfig(body: { name: string; params: FactorParams }): Promise<FactorConfig> {
  return apiPost("/api/factor/configs", body);
}

export function updateFactorConfig(id: number, body: Partial<{ name: string; params: FactorParams }>): Promise<FactorConfig> {
  return apiPatch(`/api/factor/configs/${id}`, body);
}

export function copyFactorConfig(id: number): Promise<FactorConfig> {
  return apiPost(`/api/factor/configs/${id}/copy`);
}

export function deleteFactorConfig(id: number): Promise<{ deleted: boolean }> {
  return apiDelete(`/api/factor/configs/${id}`);
}
