import { FileBarChart2, FolderKanban, LayoutDashboard } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import type { SidebarItem } from "@/components/ui/sidebar";
import {
  createEvaluationTargetModel,
  deleteEvaluationTargetModel,
  deleteOrganizationModel,
  updateEvaluationTargetModel,
  updateOrganizationModel
} from "@/services/backend-api";
import type { CreateEvaluationTargetInput as CreateEvaluationTargetModelInput, MenuType } from "@/types/accessibility-domain";

import type { DashboardRouteState } from "./types";
import { useDashboardData } from "./use-dashboard-data";
import { useDashboardTheme } from "./use-dashboard-theme";
import { useEvaluationTargetRescan } from "./use-evaluation-target-rescan";
import { useOrganizationModelCreateForm } from "./use-organization-model-create-form";
import { formatDateTime } from "./utils";

function parseDashboardRoute(pathname: string): DashboardRouteState {
  const segments = pathname.split("/").filter(Boolean);

  if (segments[0] === "reports") {
    return {
      menu: "reports" as MenuType,
      selectedOrganizationModelId: null,
      selectedEvaluationTargetModelId: null
    };
  }

  if (segments[0] === "projects") {
    const projectId = segments[1] ? Number(segments[1]) : null;
    const siteId = (segments[2] === "pages" || segments[2] === "sites") && segments[3] ? Number(segments[3]) : null;

    return {
      menu: "projects" as MenuType,
      selectedOrganizationModelId: projectId && !Number.isNaN(projectId) ? projectId : null,
      selectedEvaluationTargetModelId: siteId && !Number.isNaN(siteId) ? siteId : null
    };
  }

  return {
    menu: "dashboard" as MenuType,
    selectedOrganizationModelId: null,
    selectedEvaluationTargetModelId: null
  };
}

export function useDashboardController({
  onBootstrapComplete
}: {
  onBootstrapComplete?: () => void;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const { isDarkMode, themeMode, setThemeMode } = useDashboardTheme();
  const routeState = useMemo(() => parseDashboardRoute(location.pathname), [location.pathname]);
  const { dashboardData, dashboardError, isDashboardLoading, loadDashboard, setDashboardError } = useDashboardData({
    onBootstrapComplete
  });

  const [isSiteCreateOpen, setIsSiteCreateOpen] = useState(false);
  const handleOrganizationModelCreated = useCallback(() => {
    navigate("/projects");
  }, [navigate]);
  const organizationCreateForm = useOrganizationModelCreateForm({
    loadDashboard,
    onCreated: handleOrganizationModelCreated
  });

  const selectedOrganizationModel = useMemo(() => {
    if (routeState.selectedOrganizationModelId === null) {
      return null;
    }

    return dashboardData?.organizations.find((organization) => organization.id === routeState.selectedOrganizationModelId) ?? null;
  }, [dashboardData?.organizations, routeState.selectedOrganizationModelId]);

  const selectedEvaluationTargetModel = useMemo(() => {
    if (!selectedOrganizationModel || routeState.selectedEvaluationTargetModelId === null) {
      return null;
    }

    return (
      selectedOrganizationModel.evaluationTargets.find((target) => target.id === routeState.selectedEvaluationTargetModelId) ?? null
    );
  }, [routeState.selectedEvaluationTargetModelId, selectedOrganizationModel]);

  const isProjectDetailView =
    routeState.menu === "projects" &&
    selectedOrganizationModel !== null &&
    selectedEvaluationTargetModel === null;
  const isSiteDetailView =
    routeState.menu === "projects" &&
    selectedOrganizationModel !== null &&
    selectedEvaluationTargetModel !== null;

  useEffect(() => {
    if (!selectedOrganizationModel) {
      setIsSiteCreateOpen(false);
    }
  }, [selectedOrganizationModel]);

  useEffect(() => {
    if (!dashboardData || routeState.selectedOrganizationModelId === null) {
      return;
    }

    const projectStillExists = dashboardData.organizations.some((project) => project.id === routeState.selectedOrganizationModelId);
    if (!projectStillExists) {
      navigate("/projects", { replace: true });
    }
  }, [dashboardData, navigate, routeState.selectedOrganizationModelId]);

  useEffect(() => {
    if (!selectedOrganizationModel || routeState.selectedEvaluationTargetModelId === null) {
      return;
    }

    const siteStillExists = selectedOrganizationModel.evaluationTargets.some(
      (target) => target.id === routeState.selectedEvaluationTargetModelId
    );
    if (!siteStillExists) {
      navigate(`/projects/${routeState.selectedOrganizationModelId}`, { replace: true });
    }
  }, [navigate, routeState.selectedEvaluationTargetModelId, routeState.selectedOrganizationModelId, selectedOrganizationModel]);

  const handleUpdateOrganizationModel = useCallback(
    async ({ projectId, name, description }: { projectId: number; name: string; description: string }) => {
      await updateOrganizationModel({
        projectId,
        name,
        description
      });

      await loadDashboard({ clearOnError: false });
    },
    [loadDashboard]
  );

  const handleDeleteOrganizationModel = useCallback(
    async (projectId: number) => {
      await deleteOrganizationModel(projectId);

      if (routeState.selectedOrganizationModelId === projectId) {
        navigate("/projects", { replace: true });
      }

      await loadDashboard({ clearOnError: false });
    },
    [loadDashboard, navigate, routeState.selectedOrganizationModelId]
  );

  const handleCreateEvaluationTargetModel = useCallback(
    async ({ projectId, name, accessUrl }: CreateEvaluationTargetModelInput) => {
      await createEvaluationTargetModel({
        projectId,
        name,
        accessUrl
      });

      await loadDashboard({ clearOnError: false });
    },
    [loadDashboard]
  );

  const handleUpdateEvaluationTargetModel = useCallback(
    async ({
      projectId,
      siteId,
      name,
      accessUrl
    }: {
      projectId: number;
      siteId: number;
      name: string;
      accessUrl: string;
    }) => {
      await updateEvaluationTargetModel({
        projectId,
        siteId,
        name,
        accessUrl
      });

      await loadDashboard({ clearOnError: false });
    },
    [loadDashboard]
  );

  const handleDeleteEvaluationTargetModel = useCallback(
    async ({ projectId, siteId }: { projectId: number; siteId: number }) => {
      await deleteEvaluationTargetModel({
        projectId,
        siteId
      });

      await loadDashboard({ clearOnError: false });
    },
    [loadDashboard]
  );
  const { handleRescanEvaluationTargetModel, isRescanningSite } = useEvaluationTargetRescan({
    dashboardData,
    loadDashboard,
    onError: setDashboardError,
    selectedEvaluationTargetModel,
    selectedOrganizationModel
  });

  const sidebarLinks: SidebarItem[] = useMemo(
    () => [
      {
        label: "대시보드",
        href: "/dashboard",
        icon: <LayoutDashboard size={18} />,
        onClick: () => navigate("/dashboard"),
        active: routeState.menu === "dashboard"
      },
      {
        label: "프로젝트",
        href: "/projects",
        icon: <FolderKanban size={18} />,
        onClick: () => navigate("/projects"),
        active: routeState.menu === "projects" || routeState.menu === "project-create"
      },
      {
        label: "리포트",
        href: "/reports",
        icon: <FileBarChart2 size={18} />,
        onClick: () => navigate("/reports"),
        active: routeState.menu === "reports"
      }
    ],
    [navigate, routeState.menu]
  );

  const headerLabel =
    routeState.menu === "dashboard"
      ? "Dashboard"
      : routeState.menu === "reports"
        ? "Report"
        : isSiteDetailView
          ? "Page Details"
          : isProjectDetailView
            ? "Project Details"
            : "Project";
  const headerTitle =
    routeState.menu === "dashboard"
      ? "대시보드"
      : routeState.menu === "reports"
        ? "리포트"
        : isSiteDetailView
          ? selectedEvaluationTargetModel.name
          : isProjectDetailView
            ? selectedOrganizationModel.name
            : "프로젝트";
  const headerDescription = isSiteDetailView
    ? selectedEvaluationTargetModel.accessUrl
    : isProjectDetailView
      ? selectedOrganizationModel.description || "설명이 없습니다."
      : "";
  const headerDescriptionHref = isSiteDetailView ? headerDescription : "";
  const siteLatestScanLabel = useMemo(() => {
    if (!isSiteDetailView || !selectedEvaluationTargetModel) {
      return "";
    }

    const latestUpdatedAt = (dashboardData?.evaluationRequests ?? [])
      .filter((request) => request.evaluationTargetId === selectedEvaluationTargetModel.id)
      .map((request) => request.updatedAt)
      .sort((a, b) => Date.parse(b) - Date.parse(a))[0];

    return latestUpdatedAt ? formatDateTime(latestUpdatedAt) : "스캔 기록 없음";
  }, [dashboardData?.evaluationRequests, isSiteDetailView, selectedEvaluationTargetModel]);

  const goToProject = useCallback(
    (projectId: number) => {
      navigate(`/projects/${projectId}`);
    },
    [navigate]
  );
  const goToProjectsRoot = useCallback(() => {
    navigate("/projects");
  }, [navigate]);
  const goToSite = useCallback(
    (siteId: number) => {
      if (!selectedOrganizationModel) {
        return;
      }
      navigate(`/projects/${selectedOrganizationModel.id}/pages/${siteId}`);
    },
    [navigate, selectedOrganizationModel]
  );
  const goToSiteByIds = useCallback(
    ({ projectId, siteId }: { projectId: number; siteId: number }) => {
      navigate(`/projects/${projectId}/pages/${siteId}`);
    },
    [navigate]
  );
  const goBackToProject = useCallback(() => {
    if (!selectedOrganizationModel) {
      return;
    }
    navigate(`/projects/${selectedOrganizationModel.id}`);
  }, [navigate, selectedOrganizationModel]);
  return {
    dashboardData,
    dashboardError,
    goBackToProject,
    goToProject,
    goToProjectsRoot,
    goToSite,
    goToSiteByIds,
    handleCreateEvaluationTargetModel,
    handleDeleteEvaluationTargetModel,
    handleCreateOrganizationModel: organizationCreateForm.handleCreateOrganizationModel,
    handleUpdateEvaluationTargetModel,
    handleDeleteOrganizationModel,
    handleUpdateOrganizationModel,
    handleRescanEvaluationTargetModel,
    headerDescription,
    headerDescriptionHref,
    headerLabel,
    headerTitle,
    isCreatingOrganizationModel: organizationCreateForm.isCreatingOrganizationModel,
    isDashboardLoading,
    isDarkMode,
    isOrganizationCreateOpen: organizationCreateForm.isOrganizationCreateOpen,
    isRescanningSite,
    isSiteCreateOpen,
    menu: routeState.menu,
    newOrganizationModelDescription: organizationCreateForm.newOrganizationModelDescription,
    newOrganizationModelName: organizationCreateForm.newOrganizationModelName,
    openOrganizationCreateModal: organizationCreateForm.openOrganizationCreateModal,
    openSiteCreateModal: () => {
      setIsSiteCreateOpen(true);
    },
    projectCreateError: organizationCreateForm.projectCreateError,
    selectedEvaluationTargetModel,
    selectedOrganizationModel,
    siteLatestScanLabel,
    setIsOrganizationCreateOpen: organizationCreateForm.setIsOrganizationCreateOpen,
    setIsSiteCreateOpen,
    setNewOrganizationModelDescription: organizationCreateForm.setNewOrganizationModelDescription,
    setNewOrganizationModelName: organizationCreateForm.setNewOrganizationModelName,
    setThemeMode,
    sidebarLinks,
    themeMode
  };
}
