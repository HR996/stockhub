/**
 * Single-day K-line health detail page (P2-06 / US-3.3).
 *
 * Path: /day/:date  (date = YYYY-MM-DD)
 * Reads /api/health/kline/day/{date}. NOT_FOUND_TRADING_DAY renders a message,
 * not a full-page error.
 */
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Col, Descriptions, List, Row, Space, Skeleton, Statistic, Tag, Typography } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import { getDayDetail } from "@/api/health";
import { EnvelopeError } from "@/api/http";

const { Text } = Typography;

export default function KlineDayDetailPage() {
  const { date = "" } = useParams<{ date: string }>();
  const navigate = useNavigate();

  const { data, error, isLoading } = useQuery({
    queryKey: ["health", "kline", "day", date],
    queryFn: () => getDayDetail(date),
    enabled: !!date,
    retry: false,
  });

  const notATradingDay = error instanceof EnvelopeError && error.code === "NOT_FOUND_TRADING_DAY";

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card
        title={<span className="section-title"><span className="bar" />{`单日健康详情 · ${date}`}</span>}
        extra={
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
            返回
          </Button>
        }
      >
        {isLoading && <Skeleton active />}
        {notATradingDay && (
          <Alert
            type="info"
            showIcon
            message={`${date} 不是交易日`}
            description="非交易日没有 K 线更新，因此不生成单日详情。"
          />
        )}
        {error && !notATradingDay && (
          <Alert type="error" showIcon message="加载失败" description={String(error)} />
        )}
        {data && (
          <>
            <Row gutter={16}>
              <Col span={6}><Statistic title="应更新" value={data.expected_count} /></Col>
              <Col span={6}><Statistic title="成功" value={data.success_count} valueStyle={{ color: "#16a34a" }} /></Col>
              <Col span={6}><Statistic title="缺失" value={data.missing_count} valueStyle={{ color: "#f59e0b" }} /></Col>
              <Col span={6}><Statistic title="异常" value={data.error_count} valueStyle={{ color: "#dc2626" }} /></Col>
            </Row>
            {data.latest_task && (
              <Descriptions size="small" bordered column={2} style={{ marginTop: 16 }}>
                <Descriptions.Item label="最近一次任务">
                  <Tag color="blue">{data.latest_task.status ?? "—"}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="完成时间">
                  {data.latest_task.finished_at
                    ? dayjs(data.latest_task.finished_at).format("YYYY-MM-DD HH:mm:ss")
                    : "—"}
                </Descriptions.Item>
                {data.latest_task.error_summary && (
                  <Descriptions.Item label="错误摘要" span={2}>
                    <Text code>{JSON.stringify(data.latest_task.error_summary)}</Text>
                  </Descriptions.Item>
                )}
              </Descriptions>
            )}
          </>
        )}
      </Card>

      {data && (
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Card title={`缺失股票（前 ${data.missing_ts_codes.length} 条）`} size="small">
              <List
                size="small"
                dataSource={data.missing_ts_codes}
                locale={{ emptyText: "无" }}
                renderItem={(ts) => <List.Item>{ts}</List.Item>}
                style={{ maxHeight: 320, overflow: "auto" }}
              />
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card title={`异常股票（前 ${data.error_ts_codes.length} 条）`} size="small">
              <List
                size="small"
                dataSource={data.error_ts_codes}
                locale={{ emptyText: "无" }}
                renderItem={(ts) => <List.Item>{ts}</List.Item>}
                style={{ maxHeight: 320, overflow: "auto" }}
              />
            </Card>
          </Col>
        </Row>
      )}
    </Space>
  );
}
