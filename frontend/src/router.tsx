/**
 * Router — public routes vs. auth-guarded routes.
 *
 * `/login` is public. Everything else is nested under <AppLayout /> and
 * guarded by <RequireAuth />, which redirects unauthenticated users to /login.
 */
import { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import AppLayout from "@/components/AppLayout";
import BrowseListPage from "@/pages/BrowseListPage";
import BrowseTablePage from "@/pages/BrowseTablePage";
import DashboardPage from "@/pages/DashboardPage";
import FactorPage from "@/pages/FactorPage";
import HistoryPage from "@/pages/HistoryPage";
import IndustryPage from "@/pages/IndustryPage";
import KlineDayDetailPage from "@/pages/KlineDayDetailPage";
import LoginPage from "@/pages/LoginPage";
import StockDetailPage from "@/pages/StockDetailPage";
import { useAuthStore } from "@/store/authStore";

function RequireAuth({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="day/:date" element={<KlineDayDetailPage />} />
        <Route path="industry" element={<IndustryPage />} />
        <Route path="browse" element={<BrowseListPage />} />
        <Route path="browse/:tableKey" element={<BrowseTablePage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="stocks/:tsCode" element={<StockDetailPage />} />
        <Route path="factor" element={<FactorPage />} />
        <Route path="factor/results/:resultId" element={<FactorPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
