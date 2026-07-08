/**
 * Data-update task log table (P2-06).
 *
 * Backed by `/api/health/tasks`. Supports client-controlled pagination + sort
 * on the whitelisted columns (started_at / finished_at / task_type / status).
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Table, Tag } from "antd";
import type { ColumnsType, TablePaginationConfig } from "antd/es/table";
import type { SorterResult } from "antd/es/table/interface";
import dayjs from "dayjs";

import { getTasks, TaskRow } from "@/api/health";

const STATUS_COLOR: Record<string, string> = {
  SUCCESS: "success",
  RUNNING: "processing",
  PARTIAL: "warning",
  FAILED: "error",
};

type OrderField = "started_at" | "finished_at" | "task_type" | "status";
const ORDER_FIELDS: OrderField[] = ["started_at", "finished_at", "task_type", "status"];

function isOrderField(v: unknown): v is OrderField {
  return typeof v === "string" && (ORDER_FIELDS as string[]).includes(v);
}

function fmt(ts: string | null): string {
  return ts ? dayjs(ts).format("YYYY-MM-DD HH:mm:ss") : "—";
}

export default function TasksTable() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [orderBy, setOrderBy] = useState<OrderField>("started_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");

  const { data, error, isLoading } = useQuery({
    queryKey: ["health", "tasks", page, pageSize, orderBy, order],
    queryFn: () => getTasks(page, pageSize, orderBy, order),
    placeholderData: (prev) => prev,
  });

  const columns: ColumnsType<TaskRow> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "任务类型", dataIndex: "task_type", sorter: true, width: 180 },
    {
      title: "状态",
      dataIndex: "status",
      sorter: true,
      width: 100,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || "default"}>{s}</Tag>,
    },
    { title: "开始时间", dataIndex: "started_at", sorter: true, render: fmt, width: 180 },
    { title: "结束时间", dataIndex: "finished_at", sorter: true, render: fmt, width: 180 },
    { title: "应处理", dataIndex: "expected_count", width: 100 },
    { title: "成功", dataIndex: "success_count", width: 90 },
    { title: "缺失", dataIndex: "missing_count", width: 90 },
    { title: "异常", dataIndex: "error_count", width: 90 },
    { title: "触发者", dataIndex: "created_by", width: 120 },
  ];

  const onChange = (
    pagination: TablePaginationConfig,
    _filters: Record<string, unknown>,
    sorter: SorterResult<TaskRow> | SorterResult<TaskRow>[],
  ) => {
    const nextPage = pagination.current ?? 1;
    const nextSize = pagination.pageSize ?? pageSize;
    setPage(nextPage);
    setPageSize(nextSize);

    const s = Array.isArray(sorter) ? sorter[0] : sorter;
    if (s?.field && s.order && isOrderField(s.field)) {
      setOrderBy(s.field);
      setOrder(s.order === "ascend" ? "asc" : "desc");
    } else if (!s?.order) {
      // sort cleared → restore default
      setOrderBy("started_at");
      setOrder("desc");
    }
  };

  return (
    <Card title={<span className="section-title"><span className="bar" />更新任务日志</span>}>
      {error && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message="加载任务列表失败"
          description={String(error)}
        />
      )}
      <Table<TaskRow>
        rowKey="id"
        size="small"
        loading={isLoading}
        columns={columns}
        dataSource={data?.items ?? []}
        pagination={{
          current: page,
          pageSize,
          total: data?.total ?? 0,
          showSizeChanger: true,
          pageSizeOptions: ["10", "20", "50", "100"],
        }}
        onChange={onChange}
        scroll={{ x: 1200 }}
      />
    </Card>
  );
}
