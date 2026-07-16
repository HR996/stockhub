/**
 * App shell — branded dark sidebar + frosted top bar + content outlet.
 *
 * Rendered by the router for every authenticated route. Non-authenticated
 * routes (e.g. /login) render outside this layout.
 */
import { useState } from "react";
import { Layout, Menu } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  DashboardOutlined,
  TableOutlined,
  LineChartOutlined,
  LogoutOutlined,
  ApartmentOutlined,
  HistoryOutlined,
} from "@ant-design/icons";

import { useAuthStore } from "@/store/authStore";

const { Sider, Content, Footer } = Layout;

const MENU_ITEMS = [
  { key: "/", icon: <DashboardOutlined />, label: "数据看板" },
  { key: "/industry", icon: <ApartmentOutlined />, label: "申万行业" },
  { key: "/factor", icon: <LineChartOutlined />, label: "板块动量因子" },
  { key: "/browse", icon: <TableOutlined />, label: "数据浏览" },
  { key: "/history", icon: <HistoryOutlined />, label: "浏览历史" },
];

const TITLE_MAP: Record<string, string> = {
  "/": "数据看板",
  "/industry": "申万行业",
  "/factor": "板块动量因子",
  "/browse": "数据浏览",
  "/history": "浏览历史",
};

function pageTitle(pathname: string): string {
  if (pathname.startsWith("/day/")) return "单日健康详情";
  return TITLE_MAP[pathname] ?? "istock";
}

function UserAvatar({ name }: { name: string }) {
  const [failed, setFailed] = useState(false);
  const url = `https://r.hrc.woa.com/photo/150/${name}.png?default_when_absent=true`;
  if (failed || !name) {
    return <span className="user-avatar">{(name || "?").slice(0, 1).toUpperCase()}</span>;
  }
  return <img className="user-avatar" src={url} alt={name} onError={() => setFailed(true)} />;
}

export default function AppLayout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const location = useLocation();

  const selectedKey = location.pathname.startsWith("/day/")
    ? "/"
    : location.pathname.startsWith("/browse/")
      ? "/browse"
      : location.pathname.startsWith("/stocks/")
        ? "/browse"
        : location.pathname.startsWith("/factor/")
          ? "/factor"
          : location.pathname;

  return (
    <Layout className="app-shell" style={{ minHeight: "100vh" }}>
      <Sider width={232} theme="dark">
        <div className="app-brand">
          <span className="brand-logo-mark">📈</span>
          <div>
            <div className="app-brand-name">istock</div>
            <div className="app-brand-sub">QUANT ANALYTICS</div>
          </div>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={MENU_ITEMS}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>

      <Layout style={{ background: "var(--page-bg)" }}>
        <div className="app-header">
          <div className="page-title">{pageTitle(location.pathname)}</div>
          <div className="user-chip">
            <UserAvatar name={user ?? ""} />
            <span className="user-name">{user ?? "-"}</span>
            <span
              className="logout-btn"
              title="退出登录"
              onClick={() => {
                logout();
                navigate("/login", { replace: true });
              }}
            >
              <LogoutOutlined />
            </span>
          </div>
        </div>
        <Content className="app-content">
          <div className="fade-up">
            <Outlet />
          </div>
        </Content>
        <Footer className="app-footer">
          <a href="https://beian.miit.gov.cn/" target="_blank" rel="noreferrer">
            蜀ICP备2026039813号
          </a>
        </Footer>
      </Layout>
    </Layout>
  );
}
