/**
 * IndustryPage — Shenwan (SW2021) classification browser + node stocks panel.
 *
 * Two-column layout:
 *  - Left: AntD Tree of L1/L2/L3 (node key = "level::index_code")
 *  - Right (sticky): stocks under the currently selected node, fetched via
 *    /api/industry/node/{level}/{index_code}/stocks
 * Top banner: last-sync status/time/counts.
 */
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Card,
  Col,
  Empty,
  Row,
  Space,
  Spin,
  Table,
  Tag,
  Tree,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { DataNode } from "antd/es/tree";
import { Link } from "react-router-dom";

import {
  getIndustryTree,
  getLastSyncInfo,
  getNodeStocks,
  IndustryLevel,
  IndustryTree,
  LastSyncInfo,
  NodeStockList,
  NodeStockRow,
} from "@/api/industry";

const { Text, Paragraph } = Typography;

function statusColor(status: string | null): string {
  switch (status) {
    case "SUCCESS":
      return "green";
    case "RUNNING":
      return "blue";
    case "FAILED":
      return "red";
    default:
      return "default";
  }
}

function formatTs(ts: string | null): string {
  if (!ts) return "-";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
}

// Encode/decode a tree node key that carries both level and index_code so we
// know which endpoint variant to call when the user clicks a node.
function encodeKey(level: IndustryLevel, indexCode: string): string {
  return `${level}::${indexCode}`;
}

function decodeKey(key: string): { level: IndustryLevel; indexCode: string } | null {
  const [level, indexCode] = key.split("::");
  if (level !== "L1" && level !== "L2" && level !== "L3") return null;
  if (!indexCode) return null;
  return { level, indexCode };
}

function toTreeData(tree: IndustryTree | null): DataNode[] {
  if (!tree) return [];
  return tree.levels.map((l1) => ({
    key: encodeKey("L1", l1.index_code),
    title: (
      <span>
        <Text strong>{l1.industry_name}</Text>
        <Text type="secondary" style={{ marginLeft: 8 }}>
          {l1.index_code}
        </Text>
      </span>
    ),
    children: l1.children.map((l2) => ({
      key: encodeKey("L2", l2.index_code),
      title: (
        <span>
          {l2.industry_name}
          <Text type="secondary" style={{ marginLeft: 8 }}>
            {l2.index_code}
          </Text>
        </span>
      ),
      children: l2.children.map((l3) => ({
        key: encodeKey("L3", l3.index_code),
        title: (
          <span>
            {l3.industry_name}
            <Text type="secondary" style={{ marginLeft: 8 }}>
              {l3.index_code}
            </Text>
            <Tag color="geekblue" style={{ marginLeft: 8 }}>
              {l3.stock_count} 只
            </Tag>
          </span>
        ),
        isLeaf: true,
      })),
    })),
  }));
}

const STOCK_COLUMNS: ColumnsType<NodeStockRow> = [
  {
    title: "代码",
    dataIndex: "ts_code",
    key: "ts_code",
    width: 120,
    fixed: "left",
    render: (v: string) => <Link to={`/stocks/${v}`}>{v}</Link>,
  },
  {
    title: "名称",
    dataIndex: "name",
    key: "name",
    width: 140,
    render: (name: string | null) => name ?? <Text type="secondary">—</Text>,
  },
  {
    title: "一级 / 二级 / 三级",
    key: "path",
    render: (_: unknown, row: NodeStockRow) => (
      <span>
        {row.l1_name}
        <Text type="secondary"> / </Text>
        {row.l2_name}
        <Text type="secondary"> / </Text>
        {row.l3_name}
      </span>
    ),
  },
];

export default function IndustryPage() {
  const [tree, setTree] = useState<IndustryTree | null>(null);
  const [sync, setSync] = useState<LastSyncInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [nodeData, setNodeData] = useState<NodeStockList | null>(null);
  const [nodeLoading, setNodeLoading] = useState(false);
  const [nodeError, setNodeError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getIndustryTree(), getLastSyncInfo()])
      .then(([t, s]) => {
        if (cancelled) return;
        setTree(t);
        setSync(s);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedKey) {
      setNodeData(null);
      return;
    }
    const parsed = decodeKey(selectedKey);
    if (!parsed) return;
    let cancelled = false;
    setNodeLoading(true);
    setNodeError(null);
    getNodeStocks(parsed.level, parsed.indexCode)
      .then((data) => {
        if (cancelled) return;
        setNodeData(data);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setNodeError(e.message);
        setNodeData(null);
      })
      .finally(() => {
        if (!cancelled) setNodeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedKey]);

  const treeData = useMemo(() => toTreeData(tree), [tree]);
  const totalL3 = useMemo(
    () =>
      tree?.levels.reduce(
        (n, l1) => n + l1.children.reduce((m, l2) => m + l2.children.length, 0),
        0,
      ) ?? 0,
    [tree],
  );

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card size="small">
        {sync ? (
          <Space size="middle" wrap>
            <Tag color={statusColor(sync.status)}>{sync.status ?? "从未同步"}</Tag>
            <Text type="secondary">上次完成：{formatTs(sync.finished_at)}</Text>
            <Text type="secondary">
              分类 {sync.classify_success ?? "-"} / 预期 {sync.classify_expected ?? "-"}
            </Text>
            <Text type="secondary">孤立成员：{sync.orphan_count ?? 0}</Text>
            <Tag>SW2021</Tag>
            {sync.error_message ? <Text type="danger">{sync.error_message}</Text> : null}
          </Space>
        ) : (
          <Text type="secondary">加载同步状态…</Text>
        )}
      </Card>

      <Row gutter={16} align="top">
        <Col xs={24} md={11} lg={10}>
          <Card
            title={`申万分类（SW2021） · 共 ${totalL3} 个三级行业`}
            size="small"
            bodyStyle={{ paddingTop: 12 }}
          >
            {loading ? (
              <Spin />
            ) : error ? (
              <Alert type="error" showIcon message="加载失败" description={error} />
            ) : treeData.length === 0 ? (
              <Empty description="尚无数据 — 请先运行一次 SW 同步任务" />
            ) : (
              <>
                <Paragraph type="secondary" style={{ marginBottom: 12 }}>
                  点击任意节点查看该行业下的股票列表。叶子节点的徽章为直属股票数。
                </Paragraph>
                <Tree
                  treeData={treeData}
                  showLine
                  blockNode
                  virtual={false}
                  selectedKeys={selectedKey ? [selectedKey] : []}
                  onSelect={(keys) => {
                    const first = keys[0];
                    setSelectedKey(first ? String(first) : null);
                  }}
                />
              </>
            )}
          </Card>
        </Col>

        <Col xs={24} md={13} lg={14}>
          <Card
            size="small"
            title={
              nodeData ? (
                <Space size="small" wrap>
                  <Tag color={nodeData.level === "L1" ? "purple" : nodeData.level === "L2" ? "blue" : "geekblue"}>
                    {nodeData.level}
                  </Tag>
                  <Text strong>{nodeData.industry_name}</Text>
                  <Text type="secondary">{nodeData.index_code}</Text>
                  <Text type="secondary">· 共 {nodeData.total} 只</Text>
                </Space>
              ) : (
                "股票列表"
              )
            }
            style={{ position: "sticky", top: 16 }}
            bodyStyle={{ padding: nodeData?.stocks.length ? 0 : 24 }}
          >
            {nodeLoading ? (
              <div style={{ padding: 24, textAlign: "center" }}>
                <Spin />
              </div>
            ) : nodeError ? (
              <Alert type="error" showIcon message="加载失败" description={nodeError} />
            ) : !nodeData ? (
              <Empty description="选择左侧行业节点以查看股票" />
            ) : nodeData.stocks.length === 0 ? (
              <Empty description={`${nodeData.industry_name} 下暂无股票`} />
            ) : (
              <Table<NodeStockRow>
                columns={STOCK_COLUMNS}
                dataSource={nodeData.stocks}
                rowKey="ts_code"
                size="small"
                pagination={{
                  pageSize: 30,
                  showTotal: (total) => `共 ${total} 只`,
                  showSizeChanger: true,
                  pageSizeOptions: [20, 30, 50, 100],
                }}
                scroll={{ y: 480 }}
              />
            )}
          </Card>
        </Col>
      </Row>
    </Space>
  );
}
