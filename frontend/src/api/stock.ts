import { apiGet } from "@/api/http";

export interface StockDetail {
  basic: {
    ts_code: string;
    bs_code: string;
    name: string;
    market: string;
    list_date: string | null;
    delist_date: string | null;
    is_bj: boolean;
    is_common: boolean;
    is_st: boolean;
    updated_at: string | null;
  };
  latest_trade: {
    trade_date: string | null;
    trade_status: number | null;
    close_raw: number | null;
    close_qfq: number | null;
  };
  market_cap: null | {
    total_market_cap: number | null;
    circ_market_cap: number | null;
    snapshot_date: string | null;
    market_cap_source: string;
  };
  industry: {
    csrc: null;
    sw: null | {
      l1_index_code: string;
      l1_name: string;
      l2_index_code: string;
      l2_name: string;
      l3_index_code: string;
      l3_name: string;
      in_date: string | null;
    };
  };
}

export interface StockKlineItem {
  trade_date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  amount: number | null;
  trade_status: number;
}

export function getStockDetail(tsCode: string): Promise<StockDetail> {
  return apiGet(`/api/stocks/${tsCode}`);
}

export function getStockKline(
  tsCode: string,
  params: { start?: string; end?: string; adjust?: "raw" | "qfq" | "hfq" },
): Promise<{ ts_code: string; adjust: string; items: StockKlineItem[] }> {
  return apiGet(`/api/stocks/${tsCode}/kline`, params);
}
