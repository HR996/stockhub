import { useEffect, useState } from "react";
import { Alert, Button, Card, DatePicker, Drawer, Form, Input, InputNumber, Modal, Radio, Select, Space, Table, Tabs, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { Link, useParams } from "react-router-dom";

import {
  FactorConfig,
  FactorLevel,
  FactorParams,
  FactorRow,
  FactorStockRow,
  calculateFactor,
  createFactorConfig,
  deleteFactorConfig,
  getFactorChildren,
  getFactorConfigs,
  getFactorResult,
  getFactorResults,
  getFactorSectorStocks,
  recalculateFactor,
} from "@/api/factor";

const { Text, Title } = Typography;

const DEFAULT_PARAMS: FactorParams = {
  basedate: dayjs().format("YYYY-MM-DD"),
  window: 20,
  top_ratio: 0.15,
  classification: "SW",
  level: "L2",
  return_method: "simple",
  score_method: "median_return_score",
};

export default function FactorPage() {
  const { resultId } = useParams();
  const [form] = Form.useForm<FactorParams>();
  const [result, setResult] = useState<Awaited<ReturnType<typeof calculateFactor>> | null>(null);
  const [level, setLevel] = useState<FactorLevel>("L2");
  const [history, setHistory] = useState<Awaited<ReturnType<typeof getFactorResults>>["items"]>([]);
  const [configs, setConfigs] = useState<FactorConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [stocks, setStocks] = useState<FactorStockRow[] | null>(null);
  const [stockTitle, setStockTitle] = useState("");
  const [breadcrumb, setBreadcrumb] = useState<string[]>(["因子结果"]);

  const loadHistory = () => getFactorResults().then((r) => setHistory(r.items));
  const loadConfigs = () => getFactorConfigs().then((r) => setConfigs(r.items));
  useEffect(() => { loadHistory(); loadConfigs(); }, []);
  useEffect(() => {
    if (!resultId) return;
    getFactorResult(Number(resultId)).then((r) => {
      setResult(r);
      setLevel(r.level);
      form.setFieldsValue({ ...r.result.params, basedate: r.result.basedate });
    });
  }, [form, resultId]);

  function run(values: FactorParams) {
    const params = { ...values, basedate: dayjs(values.basedate).format("YYYY-MM-DD"), classification: "SW" as const };
    setLoading(true);
    calculateFactor(params)
      .then((r) => {
        setResult(r);
        setLevel(r.level);
        setBreadcrumb(["因子结果"]);
        loadHistory();
      })
      .catch((e: Error) => message.error(e.message))
      .finally(() => setLoading(false));
  }

  function switchLevel(next: FactorLevel) {
    if (!result) return;
    getFactorResult(result.result.id, next).then((r) => {
      setResult(r);
      setLevel(next);
      setBreadcrumb(["因子结果", next]);
    });
  }

  function drill(row: FactorRow) {
    if (!result) return;
    getFactorChildren(result.result.id, row.level, row.sector_code).then((r) => {
      setResult({ result: result.result, level: r.level, rows: r.rows });
      setLevel(r.level);
      setBreadcrumb((b) => [...b, `${row.level} ${row.sector_name}`]);
    });
  }

  function openStocks(row: FactorRow) {
    if (!result) return;
    getFactorSectorStocks(result.result.id, row.level, row.sector_code).then((r) => {
      setStocks(r.stocks);
      setStockTitle(`${row.level} ${row.sector_name}`);
      setBreadcrumb((b) => [...b, "板块股票"]);
    });
  }

  function saveConfig() {
    const params = form.getFieldsValue();
    Modal.confirm({
      title: "保存配置",
      content: <Input id="factor-config-name" placeholder="配置名称" />,
      onOk: () => {
        const input = document.getElementById("factor-config-name") as HTMLInputElement | null;
        return createFactorConfig({ name: input?.value || "未命名配置", params: { ...DEFAULT_PARAMS, ...params, basedate: dayjs(params.basedate).format("YYYY-MM-DD") } }).then(loadConfigs);
      },
    });
  }

  const rows = result?.rows ?? [];
  const columns: ColumnsType<FactorRow> = [
    { title: "板块代码", dataIndex: "sector_code", width: 120 },
    { title: "板块名称", dataIndex: "sector_name", width: 160 },
    { title: "有效股票", dataIndex: "sector_stock_count", sorter: (a, b) => a.sector_stock_count - b.sector_stock_count },
    { title: "Top 股票", dataIndex: "sector_top_stock_count", sorter: (a, b) => a.sector_top_stock_count - b.sector_top_stock_count },
    { title: "密度", dataIndex: "top_density", render: (v) => `${(v * 100).toFixed(2)}%`, sorter: (a, b) => a.top_density - b.top_density },
    { title: "中位收益", dataIndex: "median_return", render: (v) => v == null ? "-" : `${(v * 100).toFixed(2)}%`, sorter: (a, b) => (a.median_return ?? 0) - (b.median_return ?? 0) },
    { title: "得分", dataIndex: "momentum_score", sorter: (a, b) => a.momentum_score - b.momentum_score, defaultSortOrder: "descend" },
    { title: "样本", dataIndex: "small_sample_flag", render: (v) => v ? <Tag color="orange">小样本</Tag> : <Tag color="green">正常</Tag> },
    {
      title: "操作",
      fixed: "right",
      render: (_, row) => (
        <Space>
          {row.level !== "L3" ? <Button size="small" onClick={() => drill(row)}>子级</Button> : null}
          <Button size="small" onClick={() => openStocks(row)}>股票</Button>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card size="small">
        <Form form={form} layout="inline" initialValues={DEFAULT_PARAMS} onFinish={run}>
          <Form.Item name="basedate" label="基准日" getValueProps={(v) => ({ value: v ? dayjs(v) : undefined })}>
            <DatePicker />
          </Form.Item>
          <Form.Item name="window" label="窗口"><InputNumber min={1} max={250} /></Form.Item>
          <Form.Item name="top_ratio" label="Top比例"><InputNumber min={0.01} max={1} step={0.01} /></Form.Item>
          <Form.Item name="level" label="层级"><Select style={{ width: 90 }} options={["L1", "L2", "L3"].map((v) => ({ label: v, value: v }))} /></Form.Item>
          <Form.Item name="return_method" label="收益"><Select style={{ width: 110 }} options={[{ label: "simple", value: "simple" }, { label: "log", value: "log" }]} /></Form.Item>
          <Form.Item name="score_method" label="评分"><Select style={{ width: 190 }} options={[{ label: "median_return_score", value: "median_return_score" }, { label: "top_count_score", value: "top_count_score" }]} /></Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>计算</Button>
          <Button onClick={saveConfig}>保存配置</Button>
        </Form>
      </Card>

      <Tabs
        items={[
          {
            key: "result",
            label: "结果",
            children: result ? (
              <Space direction="vertical" style={{ width: "100%" }}>
                {result.result.stale ? <Alert type="warning" showIcon message={`结果可能失效：${result.result.stale_reason}`} action={<Button onClick={() => recalculateFactor(result.result.id).then(setResult)}>重新计算</Button>} /> : null}
                <Card size="small">
                  <Space wrap>
                    <Text strong>{breadcrumb.join(" › ")}</Text>
                    <Tag>{result.result.basedate} → {result.result.start_date}</Tag>
                    <Tag>SW2021</Tag>
                    <Radio.Group value={level} onChange={(e) => switchLevel(e.target.value)} options={["L1", "L2", "L3"].map((v) => ({ label: v, value: v }))} />
                  </Space>
                </Card>
                <Table size="small" rowKey="id" columns={columns} dataSource={rows} scroll={{ x: "max-content" }} />
              </Space>
            ) : <Card><Title level={5}>选择参数后开始计算</Title></Card>,
          },
          {
            key: "history",
            label: "历史",
            children: <Table size="small" rowKey="id" dataSource={history} columns={[
              { title: "ID", dataIndex: "id" },
              { title: "基准日", dataIndex: "basedate" },
              { title: "状态", dataIndex: "stale", render: (v) => v ? <Tag color="orange">失效</Tag> : <Tag color="green">有效</Tag> },
              { title: "创建人", dataIndex: "created_by" },
              { title: "操作", render: (_, row) => <Button size="small" onClick={() => getFactorResult(row.id).then(setResult)}>打开</Button> },
            ]} />,
          },
          {
            key: "configs",
            label: "配置",
            children: <Table size="small" rowKey="id" dataSource={configs} columns={[
              { title: "名称", dataIndex: "name" },
              { title: "更新", dataIndex: "updated_at" },
              { title: "操作", render: (_, row) => <Space><Button size="small" onClick={() => form.setFieldsValue(row.params)}>加载</Button><Button size="small" danger onClick={() => deleteFactorConfig(row.id).then(loadConfigs)}>删除</Button></Space> },
            ]} />,
          },
        ]}
      />

      <Drawer title={stockTitle} open={stocks !== null} onClose={() => setStocks(null)} width={720}>
        <Table
          size="small"
          rowKey="ts_code"
          dataSource={stocks ?? []}
          columns={[
            { title: "代码", dataIndex: "ts_code", render: (v) => <Link to={`/stocks/${v}`}>{v}</Link> },
            { title: "名称", dataIndex: "stock_name" },
            { title: "收益", dataIndex: "stock_return", render: (v) => v == null ? "-" : `${(v * 100).toFixed(2)}%` },
            { title: "Top", dataIndex: "is_top", render: (v) => v ? <Tag color="red">Top</Tag> : null },
            { title: "缺失原因", dataIndex: "missing_reason" },
          ]}
        />
      </Drawer>
    </Space>
  );
}
