import { useEffect, useState } from "react";
import { Card, Col, Row, Space, Spin, Typography } from "antd";
import { DatabaseOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

import { BrowseTableSpec, getBrowseTables } from "@/api/browse";

const { Text, Title } = Typography;

export default function BrowseListPage() {
  const [tables, setTables] = useState<BrowseTableSpec[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    getBrowseTables().then((r) => setTables(r.items)).finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin />;
  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Title level={4} style={{ margin: 0 }}>数据浏览</Title>
      <Row gutter={[16, 16]}>
        {tables.map((table) => (
          <Col xs={24} md={12} xl={8} key={table.key}>
            <Card hoverable onClick={() => navigate(`/browse/${table.key}`)}>
              <Space align="start">
                <DatabaseOutlined style={{ fontSize: 22, color: "var(--brand-1)" }} />
                <div>
                  <Text strong>{table.title}</Text>
                  <div><Text type="secondary">{table.key}</Text></div>
                  <div style={{ marginTop: 8 }}>{table.description}</div>
                </div>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>
    </Space>
  );
}
