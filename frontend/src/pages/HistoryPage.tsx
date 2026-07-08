import { useEffect, useState } from "react";
import { Button, Card, Popconfirm, Space, Table, Typography } from "antd";
import { useNavigate } from "react-router-dom";

import { BrowseHistoryItem, clearBrowseHistory, deleteBrowseHistory, getBrowseHistory } from "@/api/browse";

const { Text } = Typography;

export default function HistoryPage() {
  const [items, setItems] = useState<BrowseHistoryItem[]>([]);
  const navigate = useNavigate();
  const load = () => getBrowseHistory().then((r) => setItems(r.items));
  useEffect(() => { load(); }, []);

  return (
    <Card title="浏览历史" extra={<Popconfirm title="清空全部？" onConfirm={() => clearBrowseHistory().then(load)}><Button danger>清空</Button></Popconfirm>}>
      <Table
        size="small"
        rowKey="id"
        dataSource={items}
        columns={[
          { title: "页面", dataIndex: "page_title" },
          { title: "标识", dataIndex: "page_key", render: (v) => <Text type="secondary">{v}</Text> },
          { title: "时间", dataIndex: "visited_at", render: (v) => new Date(v).toLocaleString("zh-CN", { hour12: false }) },
          {
            title: "操作",
            render: (_, row) => (
              <Space>
                <Button size="small" onClick={() => navigate(`/${row.page_key.replace(":", "/")}`, { state: { page_state: row.page_state } })}>恢复</Button>
                <Button size="small" danger onClick={() => deleteBrowseHistory(row.id).then(load)}>删除</Button>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
