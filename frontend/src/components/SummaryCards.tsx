/**
 * Core-table summary cards (P2-06).
 *
 * Reads `/api/health/summary` and renders one gradient stat card per table
 * with row count and last-updated timestamp, plus a wide task-run card.
 */
import { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Col, Row, Skeleton } from "antd";
import {
  DatabaseOutlined,
  CalendarOutlined,
  LineChartOutlined,
  FundOutlined,
  HistoryOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";

import { getSummary, HealthSummary, TableSummary } from "@/api/health";

interface CardDef {
  key: keyof HealthSummary;
  title: string;
  icon: ReactNode;
  grad: string;
}

const CARDS: CardDef[] = [
  { key: "stock_basic", title: "股票基础信息", icon: <DatabaseOutlined />, grad: "grad-sky" },
  { key: "trade_calendar", title: "交易日历", icon: <CalendarOutlined />, grad: "grad-indigo" },
  { key: "k_line_daily", title: "日 K 线", icon: <LineChartOutlined />, grad: "grad-violet" },
  { key: "latest_market_cap", title: "最新市值", icon: <FundOutlined />, grad: "grad-emerald" },
];

function formatUpdated(ts: string | null): string {
  return ts ? dayjs(ts).format("YYYY-MM-DD HH:mm") : "—";
}

function StatCard({
  title,
  icon,
  grad,
  value,
  foot,
  delay,
}: {
  title: string;
  icon: ReactNode;
  grad: string;
  value: number | string;
  foot: string;
  delay: number;
}) {
  return (
    <div className="stat-card fade-up" style={{ animationDelay: `${delay}ms` }}>
      <span className={`stat-icon ${grad}`}>{icon}</span>
      <div className="stat-label">{title}</div>
      <div className="stat-value">{typeof value === "number" ? value.toLocaleString() : value}</div>
      <div className="stat-foot">{foot}</div>
    </div>
  );
}

export default function SummaryCards() {
  const { data, error, isLoading } = useQuery({
    queryKey: ["health", "summary"],
    queryFn: getSummary,
  });

  if (isLoading) return <Skeleton active />;
  if (error) return <Alert type="error" showIcon message="加载健康摘要失败" description={String(error)} />;
  if (!data) return null;

  return (
    <Row gutter={[16, 16]}>
      {CARDS.map((c, i) => {
        const s: TableSummary = data[c.key];
        return (
          <Col key={c.key} xs={24} sm={12} lg={6}>
            <StatCard
              title={c.title}
              icon={c.icon}
              grad={c.grad}
              value={s.count}
              foot={`最后更新：${formatUpdated(s.last_updated)}`}
              delay={i * 70}
            />
          </Col>
        );
      })}
      <Col xs={24}>
        <StatCard
          title="最近任务记录"
          icon={<HistoryOutlined />}
          grad="grad-amber"
          value={`${data.latest_task.count} 条`}
          foot={`最后一次任务开始：${formatUpdated(data.latest_task.last_updated)}`}
          delay={CARDS.length * 70}
        />
      </Col>
    </Row>
  );
}
