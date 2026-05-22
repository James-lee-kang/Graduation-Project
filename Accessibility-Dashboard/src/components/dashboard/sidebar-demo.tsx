import { Sidebar, SidebarBody, SidebarLink } from "@/components/ui/sidebar";
import { ToggleTheme } from "@/components/ui/toggle-theme";
import { MenuToggleIcon } from "@/components/ui/menu-toggle-icon";
import { LogOut, Plus, RefreshCw } from "lucide-react";
import { Suspense, lazy, useState } from "react";

import { OrganizationModelCreateModal } from "./modals/organization-model-create-modal";
import { SiteCreateModal } from "./modals/site-create-modal";
import { BridgeLogo } from "./shared/display";
import { useDashboardController } from "./shared/use-dashboard-controller";
import type { SidebarDemoProps } from "./shared/types";

const DashboardPanel = lazy(() => import("./panels/dashboard-panel").then((module) => ({ default: module.DashboardPanel })));
const OrganizationModelDetailPanel = lazy(() =>
  import("./panels/project-detail-panel").then((module) => ({ default: module.OrganizationModelDetailPanel }))
);
const OrganizationModelsPanel = lazy(() =>
  import("./panels/projects-panel").then((module) => ({ default: module.OrganizationModelsPanel }))
);
const ReportsPanel = lazy(() => import("./panels/reports-panel").then((module) => ({ default: module.ReportsPanel })));
const SiteDashboardPanel = lazy(() =>
  import("./panels/site-dashboard-panel").then((module) => ({ default: module.SiteDashboardPanel }))
);

function DashboardPanelFallback() {
  return (
    <article className="rounded-[28px] border border-slate-200 bg-white p-5 text-sm text-slate-600">
      화면을 불러오는 중...
    </article>
  );
}

export function SidebarDemo({ onLogout, userName, onBootstrapComplete }: SidebarDemoProps) {
  const [open, setOpen] = useState(false);
  const dashboard = useDashboardController({ onBootstrapComplete });
  const isDashboardHome = dashboard.menu === "dashboard";
  const isProjectsRoot = dashboard.menu === "projects" && !dashboard.selectedOrganizationModel;
  const shouldShowLargeHeaderTitle = isDashboardHome || isProjectsRoot;
  const shouldShowHeaderTitle =
    dashboard.menu !== "dashboard" && !isProjectsRoot;
  const hasCompactTopZone = !shouldShowLargeHeaderTitle && !shouldShowHeaderTitle;
  const shouldShowSiteHeaderActions =
    dashboard.menu === "projects" && Boolean(dashboard.selectedEvaluationTargetModel);

  return (
    <main
      className={`bridge-dashboard ${hasCompactTopZone ? "dashboard-compact-top" : ""} min-h-screen w-full overflow-x-hidden p-0 ${
        dashboard.isDarkMode ? "" : "bg-white"
      } ${dashboard.isDarkMode ? "theme-dark" : "theme-light"}`}
    >
      <div className="dashboard-shell flex min-h-screen w-full flex-col bg-transparent md:flex-row">
        <Sidebar open={open} setOpen={setOpen}>
          <SidebarBody className="justify-between gap-6">
            <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto overflow-x-hidden">
              <BridgeLogo />
              <div className="flex flex-col gap-2">
                {dashboard.sidebarLinks.map((link) => (
                  <SidebarLink key={link.label} link={link} />
                ))}
                {onLogout && (
                  <SidebarLink
                    link={{
                      label: "로그아웃",
                      onClick: onLogout,
                      icon: <LogOut size={18} />
                    }}
                    className="sidebar-logout mt-1 hover:border-red-300 hover:text-red-700"
                  />
                )}
              </div>
            </div>
          </SidebarBody>
        </Sidebar>

        <section className="min-w-0 flex-1 overflow-visible">
          <div className="dashboard-top-zone relative px-4 sm:px-7 lg:px-10">
          <header className="dashboard-fixed-header absolute top-4 right-4 left-4 z-30 flex items-start justify-between gap-5 sm:top-7 sm:right-7 sm:left-7 lg:top-10 lg:right-10 lg:left-10">
            <div className="flex min-w-0 items-center gap-4">
              <button
                type="button"
                className="dashboard-menu-trigger inline-flex shrink-0 items-center justify-center rounded-full border border-transparent bg-transparent text-slate-900 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
                aria-label="사이드바 열기"
                aria-expanded={open}
                onClick={() => setOpen(true)}
              >
                <MenuToggleIcon open={open} className="dashboard-menu-icon relative z-10" duration={500} />
              </button>
            </div>

            {shouldShowHeaderTitle && (
              <div className="pointer-events-auto absolute left-0 right-0 top-[calc(var(--dashboard-control-size)+4.25rem)] flex min-w-0 items-start justify-between gap-6">
                <div className="min-w-0">
                  <div className="flex min-w-0 flex-wrap items-end gap-x-5 gap-y-2">
                    <h1 className="dashboard-home-title shrink-0 font-black tracking-tight text-slate-900">
                      {dashboard.headerTitle}
                    </h1>
                    {dashboard.headerDescription.length > 0 && (
                      dashboard.headerDescriptionHref ? (
                        <a
                          href={dashboard.headerDescriptionHref}
                          target="_blank"
                          rel="noreferrer"
                          className="-mb-1 inline-flex max-w-[42rem] truncate text-[0.95rem] font-medium text-[#8b95a1] underline underline-offset-4 transition-colors hover:text-slate-700"
                          title={dashboard.headerDescription}
                        >
                          {dashboard.headerDescription}
                        </a>
                      ) : (
                        <p className="-mb-1 max-w-[42rem] truncate text-[0.95rem] font-medium text-[#8b95a1]" title={dashboard.headerDescription}>
                          {dashboard.headerDescription}
                        </p>
                      )
                    )}
                  </div>
                </div>

                {shouldShowSiteHeaderActions && (
                  <div className="mt-3 flex shrink-0 items-center pr-2">
                    <div className="flex min-w-[18rem] items-center justify-between gap-2 rounded-full bg-white py-1.5 pl-3 pr-1.5 text-xs font-semibold text-slate-600">
                      <div className="min-w-0">
                        <span className="text-slate-400">최근 스캔일</span>
                        <span className="ml-2 text-slate-900">{dashboard.siteLatestScanLabel}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          void dashboard.handleRescanEvaluationTargetModel();
                        }}
                        disabled={dashboard.isRescanningSite}
                        className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full bg-[#ef6a50] px-3 text-xs font-bold text-white transition hover:bg-[#e85d43] disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <RefreshCw size={13} className={dashboard.isRescanningSite ? "animate-spin" : ""} />
                        {dashboard.isRescanningSite ? "스캔 중" : "다시 스캔"}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="flex shrink-0 items-center gap-3">
              <ToggleTheme value={dashboard.themeMode} onChange={dashboard.setThemeMode} isDark={dashboard.isDarkMode} />
              <div className="dashboard-header-account flex items-center gap-3">
                <span className="dashboard-account-avatar inline-flex shrink-0 items-center justify-center rounded-full bg-[#ef6a50] font-bold text-white">
                  {userName.slice(0, 1)}
                </span>
                <div className="hidden min-w-0 pr-2 leading-tight sm:block">
                  <p className="dashboard-account-name max-w-36 truncate font-bold text-slate-900">{userName}</p>
                  <p className="dashboard-account-role mt-0.5 font-medium text-slate-500">Admin</p>
                </div>
              </div>
            </div>
          </header>

          <div className={`dashboard-date-widget absolute ${shouldShowLargeHeaderTitle ? "flex" : "hidden"} flex-wrap items-center`}>
            <h1 className="dashboard-home-title font-black tracking-tight text-slate-900">
              {isProjectsRoot ? "Project" : "Dashboard"}
            </h1>
            {isProjectsRoot && (
              <>
                <span className="ml-6 inline-flex h-11 w-px shrink-0 translate-y-1 self-center bg-slate-300" aria-hidden="true" />
                <button
                  type="button"
                  onClick={dashboard.openOrganizationCreateModal}
                  className="project-header-create-trigger ml-4 inline-flex h-11 shrink-0 translate-y-1 items-center gap-2 rounded-2xl border border-transparent bg-[#ef6a50] px-5 text-sm font-bold text-white transition hover:bg-[#e85d43] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ef6a50]/30"
                >
                  <Plus size={18} strokeWidth={2.4} className="-ml-2" />
                  프로젝트 추가
                </button>
              </>
            )}
            {/*
              접근성 검사 시작
            */}
          </div>

          </div>

          <div className="dashboard-content-zone px-4 py-3 sm:px-7 sm:py-4 lg:px-10 lg:py-4">
          <Suspense fallback={<DashboardPanelFallback />}>
            {dashboard.menu === "dashboard" && (
              <DashboardPanel
                data={dashboard.dashboardData}
                isLoading={dashboard.isDashboardLoading}
                errorMessage={dashboard.dashboardError}
                isDarkMode={dashboard.isDarkMode}
                onSiteClick={dashboard.goToSiteByIds}
              />
            )}

            {dashboard.menu === "projects" && (
              <>
                {dashboard.selectedOrganizationModel && dashboard.selectedEvaluationTargetModel ? (
                  <SiteDashboardPanel
                    organization={dashboard.selectedOrganizationModel}
                    evaluationTarget={dashboard.selectedEvaluationTargetModel}
                    evaluationRequests={dashboard.dashboardData?.evaluationRequests ?? []}
                    analysisResults={dashboard.dashboardData?.analysisResults ?? []}
                    scoreResults={dashboard.dashboardData?.scoreResults ?? []}
                    issueResults={dashboard.dashboardData?.issueResults ?? []}
                    improvementGuides={dashboard.dashboardData?.improvementGuides ?? []}
                  />
                ) : dashboard.selectedOrganizationModel ? (
                  <OrganizationModelDetailPanel
                    organization={dashboard.selectedOrganizationModel}
                    evaluationRequests={dashboard.dashboardData?.evaluationRequests ?? []}
                    analysisResults={dashboard.dashboardData?.analysisResults ?? []}
                    scoreResults={dashboard.dashboardData?.scoreResults ?? []}
                    issueResults={dashboard.dashboardData?.issueResults ?? []}
                    isDarkMode={dashboard.isDarkMode}
                    onDeleteEvaluationTargetModel={dashboard.handleDeleteEvaluationTargetModel}
                    onOpenCreateSiteModal={dashboard.openSiteCreateModal}
                    onSiteClick={dashboard.goToSite}
                    onUpdateEvaluationTargetModel={dashboard.handleUpdateEvaluationTargetModel}
                  />
                ) : (
                  <OrganizationModelsPanel
                    organizations={dashboard.dashboardData?.organizations ?? []}
                    isLoading={dashboard.isDashboardLoading}
                    errorMessage={dashboard.dashboardError}
                    isDarkMode={dashboard.isDarkMode}
                    onUpdateOrganizationModel={dashboard.handleUpdateOrganizationModel}
                    onDeleteOrganizationModel={dashboard.handleDeleteOrganizationModel}
                    onOrganizationModelClick={dashboard.goToProject}
                  />
                )}
              </>
            )}

            {dashboard.menu === "reports" && (
              <ReportsPanel
                scoreResults={dashboard.dashboardData?.scoreResults ?? []}
                issueResults={dashboard.dashboardData?.issueResults ?? []}
                isLoading={dashboard.isDashboardLoading}
                errorMessage={dashboard.dashboardError}
              />
            )}
          </Suspense>
          </div>

          {dashboard.selectedOrganizationModel && (
            <SiteCreateModal
              isOpen={dashboard.isSiteCreateOpen}
              isDarkMode={dashboard.isDarkMode}
              project={dashboard.selectedOrganizationModel}
              onAddEvaluationTargetModel={dashboard.handleCreateEvaluationTargetModel}
              onClose={() => dashboard.setIsSiteCreateOpen(false)}
            />
          )}

          <OrganizationModelCreateModal
            isOpen={dashboard.isOrganizationCreateOpen}
            isDarkMode={dashboard.isDarkMode}
            name={dashboard.newOrganizationModelName}
            description={dashboard.newOrganizationModelDescription}
            isSubmitting={dashboard.isCreatingOrganizationModel}
            errorMessage={dashboard.projectCreateError}
            onNameChange={dashboard.setNewOrganizationModelName}
            onDescriptionChange={dashboard.setNewOrganizationModelDescription}
            onClose={() => {
              if (dashboard.isCreatingOrganizationModel) {
                return;
              }
              dashboard.setIsOrganizationCreateOpen(false);
            }}
            onSubmit={dashboard.handleCreateOrganizationModel}
          />
        </section>
      </div>
    </main>
  );
}
