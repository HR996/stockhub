import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Button, Checkbox, Drawer, Form, Input, Select, Space, Table, Tooltip } from "antd";
import type { ColumnsType, TablePaginationConfig } from "antd/es/table";
import { DndContext, DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { SettingOutlined } from "@ant-design/icons";

import { BrowseField, BrowseFilter } from "@/api/browse";

interface Props {
  fields: BrowseField[];
  rows: Record<string, unknown>[];
  total: number;
  loading?: boolean;
  page: number;
  pageSize: number;
  orderBy?: string;
  order?: "asc" | "desc";
  visibleFields: string[];
  filters: BrowseFilter[];
  onChange: (next: {
    page?: number;
    pageSize?: number;
    orderBy?: string;
    order?: "asc" | "desc";
    visibleFields?: string[];
    filters?: BrowseFilter[];
  }) => void;
  renderCell?: (field: string, value: unknown, row: Record<string, unknown>) => ReactNode;
}

function SortableField({ id, title }: { id: string; title: string }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id });
  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        padding: "6px 8px",
        border: "1px solid #e5e7eb",
        borderRadius: 6,
        marginBottom: 6,
        background: "#fff",
        cursor: "grab",
      }}
      {...attributes}
      {...listeners}
    >
      {title}
    </div>
  );
}

export default function DataTable({
  fields,
  rows,
  total,
  loading,
  page,
  pageSize,
  orderBy,
  order,
  visibleFields,
  filters,
  onChange,
  renderCell,
}: Props) {
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const fieldByKey = useMemo(() => Object.fromEntries(fields.map((f) => [f.key, f])), [fields]);

  const columns: ColumnsType<Record<string, unknown>> = visibleFields.map((key) => ({
    title: fieldByKey[key]?.title ?? key,
    dataIndex: key,
    key,
    sorter: fieldByKey[key]?.sortable,
    sortOrder: orderBy === key ? (order === "desc" ? "descend" : "ascend") : null,
    ellipsis: true,
    render: (value, row) => renderCell?.(key, value, row) ?? String(value ?? ""),
  }));

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = visibleFields.indexOf(String(active.id));
    const newIndex = visibleFields.indexOf(String(over.id));
    onChange({ visibleFields: arrayMove(visibleFields, oldIndex, newIndex) });
  }

  return (
    <>
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <Space wrap>
          <Button icon={<SettingOutlined />} onClick={() => setOpen(true)}>
            字段
          </Button>
          <Form
            form={form}
            layout="inline"
            onFinish={(values) => {
              const next = values.field && values.op ? [{ field: values.field, op: values.op, value: values.value }] : [];
              onChange({ page: 1, filters: next as BrowseFilter[] });
            }}
          >
            <Form.Item name="field">
              <Select placeholder="筛选字段" style={{ width: 160 }} allowClear options={fields.map((f) => ({ label: f.title, value: f.key }))} />
            </Form.Item>
            <Form.Item name="op">
              <Select
                placeholder="条件"
                style={{ width: 120 }}
                options={[
                  { label: "等于", value: "eq" },
                  { label: "包含", value: "contains" },
                  { label: "大于等于", value: "gte" },
                  { label: "小于等于", value: "lte" },
                  { label: "为空", value: "is_null" },
                ]}
              />
            </Form.Item>
            <Form.Item name="value">
              <Input placeholder="值" style={{ width: 180 }} />
            </Form.Item>
            <Button htmlType="submit">筛选</Button>
            {filters.length ? <Button onClick={() => { form.resetFields(); onChange({ page: 1, filters: [] }); }}>清除</Button> : null}
          </Form>
        </Space>
        <Table
          size="small"
          rowKey={(row) => String(row.id ?? JSON.stringify(row))}
          columns={columns}
          dataSource={rows}
          loading={loading}
          scroll={{ x: "max-content" }}
          pagination={{ current: page, pageSize, total, showSizeChanger: true }}
          onChange={(pagination: TablePaginationConfig, _filters, sorter) => {
            const s = Array.isArray(sorter) ? sorter[0] : sorter;
            onChange({
              page: pagination.current,
              pageSize: pagination.pageSize,
              orderBy: s?.field ? String(s.field) : orderBy,
              order: s?.order === "descend" ? "desc" : "asc",
            });
          }}
        />
      </Space>

      <Drawer title="字段显示与顺序" open={open} onClose={() => setOpen(false)} width={360}>
        <Checkbox.Group
          value={visibleFields}
          onChange={(values) => onChange({ visibleFields: values.map(String) })}
          style={{ display: "grid", gap: 8, marginBottom: 16 }}
        >
          {fields.map((field) => (
            <Tooltip key={field.key} title={field.description}>
              <Checkbox value={field.key}>{field.title}</Checkbox>
            </Tooltip>
          ))}
        </Checkbox.Group>
        <DndContext onDragEnd={handleDragEnd}>
          <SortableContext items={visibleFields} strategy={verticalListSortingStrategy}>
            {visibleFields.map((key) => (
              <SortableField key={key} id={key} title={fieldByKey[key]?.title ?? key} />
            ))}
          </SortableContext>
        </DndContext>
      </Drawer>
    </>
  );
}
