import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import AppRouter from "@/router";
import "@/styles/global.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const themeConfig = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: "#6366f1",
    colorInfo: "#6366f1",
    colorSuccess: "#16a34a",
    colorWarning: "#f59e0b",
    colorError: "#dc2626",
    colorLink: "#0ea5e9",
    borderRadius: 12,
    borderRadiusLG: 16,
    fontFamily:
      '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
    colorTextBase: "#1e293b",
    boxShadowSecondary: "0 6px 20px rgba(15,23,42,0.08)",
  },
  components: {
    Card: { headerFontSize: 16, paddingLG: 22 },
    Button: { controlHeight: 38, fontWeight: 600, primaryShadow: "0 8px 18px rgba(99,102,241,0.35)" },
    Menu: { darkItemBg: "transparent" },
    Table: { headerBg: "#f8fafc", borderColor: "rgba(148,163,184,0.16)" },
    Statistic: { titleFontSize: 13 },
  },
};

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={themeConfig}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  </React.StrictMode>,
);
