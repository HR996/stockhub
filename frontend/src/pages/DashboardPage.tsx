/**
 * Dashboard — 4 summary cards + K-line calendar + task log table (P2-06).
 */
import { Space } from "antd";
import { useNavigate } from "react-router-dom";

import KlineCalendar from "@/components/KlineCalendar";
import SummaryCards from "@/components/SummaryCards";
import TasksTable from "@/components/TasksTable";

export default function DashboardPage() {
  const navigate = useNavigate();

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <SummaryCards />
      <KlineCalendar onSelectDay={(date) => navigate(`/day/${date}`)} />
      <TasksTable />
    </Space>
  );
}
