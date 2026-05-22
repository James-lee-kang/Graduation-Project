import { Suspense, lazy, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

const DashboardShell = lazy(() => import("@/components/ui/sidebar-demo").then((module) => ({ default: module.SidebarDemo })));
const DEFAULT_USER_NAME = "정하진";

function DashboardRouteFallback() {
  return (
    <section className="fixed inset-0 z-[999] flex items-center justify-center bg-white">
      <div className="rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-lg">
        <p className="text-sm font-medium text-slate-700">대시보드 화면을 불러오는 중...</p>
      </div>
    </section>
  );
}

function DashboardRoute() {
  const [isDashboardBooting, setIsDashboardBooting] = useState(true);

  return (
    <>
      <Suspense fallback={<DashboardRouteFallback />}>
        <DashboardShell userName={DEFAULT_USER_NAME} onBootstrapComplete={() => setIsDashboardBooting(false)} />
      </Suspense>

      {isDashboardBooting && (
        <section className="fixed inset-0 z-[999] flex items-center justify-center bg-black/35 backdrop-blur-[2px]">
          <div className="rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-lg">
            <p className="text-sm font-medium text-slate-700">대시보드를 불러오는 중...</p>
          </div>
        </section>
      )}
    </>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/*" element={<DashboardRoute />} />
    </Routes>
  );
}

export default App;
