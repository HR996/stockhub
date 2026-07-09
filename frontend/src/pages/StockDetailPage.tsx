import { useEffect, useState } from "react";
import { Alert, Card, Descriptions, Space, Spin, Tag, Typography } from "antd";
import ReactECharts from "echarts-for-react";
import { useParams } from "react-router-dom";

import { getStockDetail, getStockKline, StockDetail, StockKlineItem } from "@/api/stock";

const { Title } = Typography;

export default function StockDetailPage() {
  const { tsCode = "" } = useParams();
  const [detail, setDetail] = useState<StockDetail | null>(null);
  const [kline, setKline] = useState<StockKlineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([getStockDetail(tsCode), getStockKline(tsCode)])
      .then(([d, k]) => { setDetail(d); setKline(k.items); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [tsCode]);

  if (loading) return <Spin />;
  if (error || !detail) return <Alert type="error" message={error ?? "加载失败"} />;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Title level={4} style={{ margin: 0 }}>{detail.basic.name} · {detail.basic.ts_code}</Title>
      <Card size="small">
        <Descriptions size="small" column={3}>
          <Descriptions.Item label="市场">{detail.basic.market}</Descriptions.Item>
          <Descriptions.Item label="上市日期">{detail.basic.list_date ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="状态">
            {detail.basic.is_bj ? <Tag>北交所</Tag> : null}
            {detail.basic.is_common ? <Tag color="green">普通股票</Tag> : <Tag>非普通</Tag>}
            {detail.basic.is_st ? <Tag color="red">ST</Tag> : null}
          </Descriptions.Item>
          <Descriptions.Item label="最新交易日">{detail.latest_trade.trade_date ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="收盘价">{detail.latest_trade.close_raw ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="总市值">{detail.market_cap?.total_market_cap ? `${(detail.market_cap.total_market_cap / 100000000).toFixed(2)} 亿` : "-"}</Descriptions.Item>
          <Descriptions.Item label="申万行业" span={3}>
            {detail.industry.sw ? `${detail.industry.sw.l1_name} / ${detail.industry.sw.l2_name} / ${detail.industry.sw.l3_name}` : "-"}
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Card size="small" title="K 线（最新基准日前复权）">
        <ReactECharts
          style={{ height: 360 }}
          option={{
            tooltip: { trigger: "axis" },
            xAxis: { type: "category", data: kline.map((x) => x.trade_date) },
            yAxis: { scale: true },
            series: [{ type: "line", data: kline.map((x) => x.close), smooth: true, showSymbol: false }],
          }}
        />
      </Card>
    </Space>
  );
}
