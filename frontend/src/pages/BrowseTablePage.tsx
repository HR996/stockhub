import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Space, Spin, Typography } from "antd";
import { Link, useLocation, useParams } from "react-router-dom";

import { BrowseFilter, BrowseTableSpec, getBrowseTables, queryBrowseTable, saveBrowseHistory } from "@/api/browse";
import DataTable from "@/components/DataTable";

const { Text, Title } = Typography;

interface TableState {
  page: number;
  pageSize: number;
  orderBy?: string;
  order?: "asc" | "desc";
  visibleFields: string[];
  filters: BrowseFilter[];
}

export default function BrowseTablePage() {
  const { tableKey = "" } = useParams();
  const location = useLocation();
  const restored = (location.state as { page_state?: Partial<TableState> } | null)?.page_state;
  const [spec, setSpec] = useState<BrowseTableSpec | null>(null);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<TableState>({
    page: restored?.page ?? 1,
    pageSize: restored?.pageSize ?? 50,
    orderBy: restored?.orderBy,
    order: restored?.order ?? "asc",
    visibleFields: restored?.visibleFields ?? [],
    filters: restored?.filters ?? [],
  });

  useEffect(() => {
    getBrowseTables().then((r) => {
      const found = r.items.find((t) => t.key === tableKey) ?? null;
      setSpec(found);
      if (found && state.visibleFields.length === 0) {
        setState((s) => ({ ...s, visibleFields: found.fields.slice(0, 8).map((f) => f.key), orderBy: found.fields[0]?.key }));
      }
    });
  }, [tableKey, state.visibleFields.length]);

  useEffect(() => {
    if (!spec || state.visibleFields.length === 0) return;
    setLoading(true);
    setError(null);
    queryBrowseTable(tableKey, {
      page: state.page,
      page_size: state.pageSize,
      order_by: state.orderBy,
      order: state.order,
      fields: state.visibleFields,
      filters: state.filters,
    })
      .then((r) => {
        setRows(r.items);
        setTotal(r.total);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [spec, tableKey, state]);

  useEffect(() => {
    if (!spec) return;
    const timer = window.setTimeout(() => {
      saveBrowseHistory({
        page_key: `browse:${tableKey}`,
        page_title: spec.title,
        page_state: state as unknown as Record<string, unknown>,
      }).catch(() => undefined);
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [spec, tableKey, state]);

  const fields = useMemo(() => spec?.fields ?? [], [spec]);
  if (!spec) return loading ? <Spin /> : <Alert type="error" message="表不存在" />;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card size="small">
        <Space direction="vertical" size={2}>
          <Title level={4} style={{ margin: 0 }}>{spec.title}</Title>
          <Text type="secondary">{spec.description}</Text>
          <Text type="secondary">{spec.key}</Text>
        </Space>
      </Card>
      {error ? <Alert type="error" message={error} /> : null}
      <DataTable
        fields={fields}
        rows={rows}
        total={total}
        loading={loading}
        page={state.page}
        pageSize={state.pageSize}
        orderBy={state.orderBy}
        order={state.order}
        visibleFields={state.visibleFields}
        filters={state.filters}
        onChange={(next) => setState((s) => ({ ...s, ...next }))}
        renderCell={(field, value) =>
          field === "ts_code" && value ? <Link to={`/stocks/${value}`}>{String(value)}</Link> : String(value ?? "")
        }
      />
      <Button href="/browse">返回表列表</Button>
    </Space>
  );
}
