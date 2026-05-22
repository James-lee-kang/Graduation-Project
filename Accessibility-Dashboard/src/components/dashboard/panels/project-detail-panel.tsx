import { ArrowDown, ArrowUp, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";
import { getApiErrorMessage } from "@/services/backend-api";
import type {
  AnalysisResult,
  EvaluationTargetModel,
  EvaluationRequestModel,
  IssueResultModel,
  OrganizationModel,
  ScoreResult
} from "@/types/accessibility-domain";

import { PanelMessage, renderTargetTypeIcon } from "../shared/display";
import { useDialogAccessibility } from "../shared/use-dialog-accessibility";
import { formatDateTime, mapScanStatus } from "../shared/utils";

type ProjectDetailSiteSortKey = "targetType" | "siteName" | "score" | "updatedAt";


export function OrganizationModelDetailPanel({
  organization,
  evaluationRequests,
  scoreResults,
  isDarkMode,
  onOpenCreateSiteModal,
  onSiteClick,
  onUpdateEvaluationTargetModel,
  onDeleteEvaluationTargetModel
}: {
  organization: OrganizationModel;
  evaluationRequests: EvaluationRequestModel[];
  analysisResults: AnalysisResult[];
  scoreResults: ScoreResult[];
  issueResults: IssueResultModel[];
  isDarkMode: boolean;
  onOpenCreateSiteModal: () => void;
  onSiteClick: (siteId: number) => void;
  onUpdateEvaluationTargetModel: (input: {
    projectId: number;
    siteId: number;
    name: string;
    accessUrl: string;
  }) => Promise<void>;
  onDeleteEvaluationTargetModel: (input: { projectId: number; siteId: number }) => Promise<void>;
}) {
  const [siteSortConfig, setSiteSortConfig] = useState<{
    key: ProjectDetailSiteSortKey;
    direction: "asc" | "desc";
  }>({
    key: "updatedAt",
    direction: "desc"
  });
  const [editingEvaluationTargetModel, setEditingEvaluationTargetModel] = useState<EvaluationTargetModel | null>(null);
  const [editSiteName, setEditSiteName] = useState("");
  const [editSiteBaseUrl, setEditSiteBaseUrl] = useState("");
  const [editEvaluationTargetError, setEditEvaluationTargetError] = useState("");
  const [isSavingEvaluationTarget, setIsSavingEvaluationTarget] = useState(false);
  const [deletingEvaluationTargetModel, setDeletingEvaluationTargetModel] = useState<EvaluationTargetModel | null>(null);
  const [deleteEvaluationTargetError, setDeleteEvaluationTargetError] = useState("");
  const [isDeletingEvaluationTarget, setIsDeletingEvaluationTarget] = useState(false);

  const evaluationTargetIds = new Set(organization.evaluationTargets.map((target) => target.id));
  const organizationEvaluationRequests = evaluationRequests.filter((request) =>
    evaluationTargetIds.has(request.evaluationTargetId)
  );
  const latestScanBySiteId = new Map<number, EvaluationRequestModel>();
  for (const evaluationRequest of organizationEvaluationRequests) {
    const existing = latestScanBySiteId.get(evaluationRequest.evaluationTargetId);
    if (!existing) {
      latestScanBySiteId.set(evaluationRequest.evaluationTargetId, evaluationRequest);
      continue;
    }

    const currentTime = Date.parse(evaluationRequest.updatedAt);
    const existingTime = Date.parse(existing.updatedAt);
    if (currentTime > existingTime) {
      latestScanBySiteId.set(evaluationRequest.evaluationTargetId, evaluationRequest);
    }
  }
  const scoreByEvaluationRequestId = new Map(scoreResults.map((scoreResult) => [scoreResult.evaluationRequestId, scoreResult]));

  const evaluationTargetById = new Map(organization.evaluationTargets.map((site) => [site.id, site]));

  const siteRows = organization.evaluationTargets.map((site) => {
    const latestScan = latestScanBySiteId.get(site.id);
    const latestScoreResult = latestScan ? scoreByEvaluationRequestId.get(latestScan.id) : undefined;

    return {
      id: site.id,
      targetType: site.targetType,
      name: site.name,
      accessUrl: site.accessUrl,
      status: latestScan ? mapScanStatus(latestScan.status) : "미진행",
      totalScore: latestScoreResult?.totalScore ?? null,
      finishedAt: latestScan?.updatedAt ?? null,
      lastUpdatedAt: latestScan?.updatedAt ?? site.createdAt
    };
  });

  const sortedSiteRows = [...siteRows].sort((a, b) => {
    const updatedDiff = Date.parse(b.lastUpdatedAt) - Date.parse(a.lastUpdatedAt);

    if (siteSortConfig.key === "siteName") {
      const siteNameDiff = a.name.localeCompare(b.name, "ko");
      if (siteNameDiff !== 0) {
        return siteSortConfig.direction === "asc" ? siteNameDiff : -siteNameDiff;
      }

      return siteSortConfig.direction === "asc" ? -updatedDiff : updatedDiff;
    }

    if (siteSortConfig.key === "targetType") {
      const targetTypeDiff = a.targetType.localeCompare(b.targetType, "ko");
      if (targetTypeDiff !== 0) {
        return siteSortConfig.direction === "asc" ? targetTypeDiff : -targetTypeDiff;
      }

      return siteSortConfig.direction === "asc" ? -updatedDiff : updatedDiff;
    }

    if (siteSortConfig.key === "score") {
      const scoreDiff = (b.totalScore ?? -1) - (a.totalScore ?? -1);
      if (scoreDiff !== 0) {
        return siteSortConfig.direction === "desc" ? scoreDiff : -scoreDiff;
      }

      return siteSortConfig.direction === "desc" ? updatedDiff : -updatedDiff;
    }

    return siteSortConfig.direction === "asc" ? -updatedDiff : updatedDiff;
  });

  const handleSiteSort = (key: ProjectDetailSiteSortKey) => {
    setSiteSortConfig((current) => {
      if (current.key === key) {
        return {
          key,
          direction: current.direction === "asc" ? "desc" : "asc"
        };
      }

      return {
        key,
        direction: key === "updatedAt" || key === "score" ? "desc" : "asc"
      };
    });
  };

  const getSiteSortIndicator = (key: ProjectDetailSiteSortKey) => {
    const isActive = siteSortConfig.key === key;

    return (
      <span
        className={cn(
          "inline-flex h-4 w-3 shrink-0 items-center justify-center leading-none",
          isActive ? "opacity-100" : "opacity-0"
        )}
      >
        {siteSortConfig.direction === "asc" ? (
          <ArrowUp size={11} strokeWidth={2.4} className="block" />
        ) : (
          <ArrowDown size={11} strokeWidth={2.4} className="block" />
        )}
      </span>
    );
  };

  const getCenteredSiteSortIndicator = (key: ProjectDetailSiteSortKey) => {
    const isActive = siteSortConfig.key === key;

    return (
      <span
        className={cn(
          "pointer-events-none absolute left-full top-1/2 ml-0.5 inline-flex h-4 w-3 -translate-y-1/2 items-center justify-center leading-none",
          isActive ? "opacity-100" : "opacity-0"
        )}
      >
        {siteSortConfig.direction === "asc" ? (
          <ArrowUp size={11} strokeWidth={2.4} className="block" />
        ) : (
          <ArrowDown size={11} strokeWidth={2.4} className="block" />
        )}
      </span>
    );
  };

  const getSiteStatusBadgeClassName = (status: string) => {
    if (status === finishedStatusLabel) {
      return "site-status-badge site-status-badge-finished";
    }
    if (status === runningStatusLabel) {
      return "site-status-badge site-status-badge-running";
    }
    if (status === failedStatusLabel) {
      return "site-status-badge site-status-badge-failed";
    }
    return "site-status-badge site-status-badge-idle";
  };

  const getTargetTypeInfo = (type: OrganizationModel["evaluationTargets"][number]["targetType"]) => {
    if (type === "모바일 웹") {
      return "모바일 웹";
    }

    if (type === "문서") {
      return "문서";
    }

    return "PC 웹";
  };

  const openEditEvaluationTargetModel = (site: EvaluationTargetModel) => {
    setEditingEvaluationTargetModel(site);
    setEditSiteName(site.name);
    setEditSiteBaseUrl(site.accessUrl);
    setEditEvaluationTargetError("");
  };

  const openDeleteEvaluationTargetModel = (site: EvaluationTargetModel) => {
    setDeletingEvaluationTargetModel(site);
    setDeleteEvaluationTargetError("");
  };

  const closeEditEvaluationTargetModel = () => {
    setEditingEvaluationTargetModel(null);
    setEditEvaluationTargetError("");
  };

  const closeDeleteEvaluationTargetModel = () => {
    setDeletingEvaluationTargetModel(null);
    setDeleteEvaluationTargetError("");
  };

  const editDialogRef = useDialogAccessibility({
    isOpen: editingEvaluationTargetModel !== null,
    onClose: closeEditEvaluationTargetModel,
    closeDisabled: isSavingEvaluationTarget
  });
  const deleteDialogRef = useDialogAccessibility({
    isOpen: deletingEvaluationTargetModel !== null,
    onClose: closeDeleteEvaluationTargetModel,
    closeDisabled: isDeletingEvaluationTarget
  });

  const handleSaveEvaluationTargetModel = async () => {
    if (!editingEvaluationTargetModel) {
      return;
    }

    const name = editSiteName.trim();
    const accessUrl = editSiteBaseUrl.trim();

    if (name.length === 0 || accessUrl.length === 0) {
      setEditEvaluationTargetError("페이지 이름과 주소는 필수입니다.");
      return;
    }

    setIsSavingEvaluationTarget(true);
    setEditEvaluationTargetError("");

    try {
      await onUpdateEvaluationTargetModel({
        projectId: organization.id,
        siteId: editingEvaluationTargetModel.id,
        name,
        accessUrl
      });

      closeEditEvaluationTargetModel();
    } catch (error) {
      setEditEvaluationTargetError(getApiErrorMessage(error, "페이지 수정 중 오류가 발생했습니다."));
    } finally {
      setIsSavingEvaluationTarget(false);
    }
  };

  const handleConfirmDeleteEvaluationTargetModel = async () => {
    if (!deletingEvaluationTargetModel) {
      return;
    }

    setIsDeletingEvaluationTarget(true);
    setDeleteEvaluationTargetError("");

    try {
      await onDeleteEvaluationTargetModel({
        projectId: organization.id,
        siteId: deletingEvaluationTargetModel.id
      });

      closeDeleteEvaluationTargetModel();
    } catch (error) {
      setDeleteEvaluationTargetError(getApiErrorMessage(error, "페이지 제거 중 오류가 발생했습니다."));
    } finally {
      setIsDeletingEvaluationTarget(false);
    }
  };

  const finishedStatusLabel = mapScanStatus("finished");
  const failedStatusLabel = mapScanStatus("failed");
  const runningStatusLabel = mapScanStatus("queued");

  return (
    <div className="space-y-3 overflow-visible">
      <div className="absolute right-[var(--dashboard-side-gutter)] top-[calc(var(--dashboard-fixed-top)+var(--dashboard-control-size)+5.75rem)] z-50">
        <button
          type="button"
          onClick={onOpenCreateSiteModal}
          className="inline-flex h-11 shrink-0 items-center gap-2 rounded-2xl border border-transparent bg-[#ef6a50] px-5 text-sm font-bold text-white transition hover:bg-[#e85d43] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ef6a50]/30"
        >
          <Plus size={18} strokeWidth={2.4} className="-ml-2" />
          페이지 추가
        </button>
      </div>

      <div className="space-y-0">
          <div className="project-list-table overflow-visible bg-transparent">
            <div className="overflow-visible">
              <table className="w-full table-fixed text-left">
              <colgroup>
                <col className="w-[52px]" />
                <col className="w-[23%]" />
                <col className="w-[34%]" />
                <col className="w-[120px]" />
                <col className="w-[110px]" />
                <col className="w-[160px]" />
                <col className="w-[6%]" />
              </colgroup>
              <thead className="project-list-head border-b border-slate-200/80 text-xs text-slate-500">
                <tr>
                  <th className="h-8 py-0 font-medium text-center align-middle">
                    <button
                      type="button"
                      onClick={() => handleSiteSort("targetType")}
                      className="flex h-8 w-full items-center justify-center px-0 text-center cursor-pointer select-none"
                    >
                      <span className="relative inline-flex -translate-x-3 items-center justify-center">
                        종류
                        {getCenteredSiteSortIndicator("targetType")}
                      </span>
                    </button>
                  </th>
                  <th className="h-8 py-0 font-medium align-middle">
                    <button
                      type="button"
                      onClick={() => handleSiteSort("siteName")}
                      className="-ml-5 flex h-8 w-full items-center gap-0.5 px-0 text-left cursor-pointer select-none"
                    >
                      페이지 이름
                      {getSiteSortIndicator("siteName")}
                    </button>
                  </th>
                  <th className="h-8 px-4 py-0 font-medium align-middle">주소</th>
                  <th className="h-8 px-4 py-0 font-medium text-center align-middle">상태</th>
                  <th className="h-8 py-0 font-medium text-center align-middle">
                    <button
                      type="button"
                      onClick={() => handleSiteSort("score")}
                      className="flex h-8 w-full items-center justify-center px-4 text-center cursor-pointer select-none"
                    >
                      <span className="relative inline-flex items-center justify-center">
                        최근 점수
                        {getCenteredSiteSortIndicator("score")}
                      </span>
                    </button>
                  </th>
                  <th className="h-8 py-0 font-medium align-middle">
                    <button
                      type="button"
                      onClick={() => handleSiteSort("updatedAt")}
                      className="flex h-8 w-full items-center gap-0.5 px-4 text-left cursor-pointer select-none"
                    >
                      최근 완료 시각
                      {getSiteSortIndicator("updatedAt")}
                    </button>
                  </th>
                  <th className="h-8 px-4 py-0 align-middle" aria-label="페이지 액션" />
                </tr>
              </thead>
              <tbody>
                {sortedSiteRows.length === 0 ? (
                  <tr className="project-list-row">
                    <td colSpan={7} className="px-4 py-6 text-center text-xs text-slate-500">
                      등록된 페이지가 없습니다.
                    </td>
                  </tr>
                ) : (
                  sortedSiteRows.map((row, index) => (
                    <tr
                      key={row.id}
                      onClick={() => onSiteClick(row.id)}
                      className={`project-list-row group cursor-pointer ${
                        index !== sortedSiteRows.length - 1 ? "border-b border-slate-200/80" : ""
                      }`}
                    >
                      <td className="relative px-0 py-1.5 align-middle text-slate-600">
                        <div className="group/target-type relative flex -translate-x-3 items-center justify-center">
                          <span
                            className={`inline-flex h-7 w-7 items-center justify-center rounded-full transition ${
                              isDarkMode ? "group-hover/target-type:bg-white/[0.06]" : "group-hover/target-type:bg-slate-100"
                            }`}
                            aria-label={getTargetTypeInfo(row.targetType)}
                          >
                            {renderTargetTypeIcon(row.targetType)}
                          </span>
                          <span
                            data-tooltip-tone={isDarkMode ? "dark" : "light"}
                            className="project-table-tooltip invisible pointer-events-none absolute left-1/2 top-full z-[9999] mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-medium group-hover/target-type:visible"
                          >
                            {getTargetTypeInfo(row.targetType)}
                          </span>
                        </div>
                      </td>
                      <td className="px-0 py-1.5 align-middle">
                        <div className="-ml-5 min-w-0">
                          <p className="truncate text-xs font-semibold text-slate-900">{row.name}</p>
                        </div>
                      </td>
                      <td className="px-4 py-1.5 align-middle">
                        <a
                          href={row.accessUrl}
                          target="_blank"
                          rel="noreferrer"
                          title={row.accessUrl}
                          onClick={(event) => event.stopPropagation()}
                          className="inline-block max-w-full truncate text-xs leading-4 text-slate-600 hover:underline"
                        >
                          {row.accessUrl}
                        </a>
                      </td>
                      <td className="px-4 py-1.5 align-middle">
                        <div className="flex items-center justify-center">
                          <span
                            className={cn(
                              "inline-flex items-center rounded-md px-2.5 py-1 text-[11px] font-semibold",
                              getSiteStatusBadgeClassName(row.status)
                            )}
                          >
                            {row.status}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-1.5 align-middle text-center">
                        <span className="text-xs font-medium text-slate-700">
                          {row.totalScore !== null ? `${row.totalScore}점` : "-"}
                        </span>
                      </td>
                      <td className="project-list-updated px-4 py-1.5 align-middle text-xs tabular-nums text-slate-500">
                        {formatDateTime(row.finishedAt)}
                      </td>
                      <td className="relative px-4 py-1.5 text-right align-middle">
                        <div className="group/project-actions absolute right-4 top-1/2 flex h-9 w-[106px] -translate-y-1/2 items-center justify-end">
                          <div className="pointer-events-none absolute right-9 top-1/2 inline-flex h-9 w-[68px] -translate-y-1/2 items-center justify-end gap-1 opacity-0 transition-all duration-200 ease-out group-hover/project-actions:pointer-events-auto group-hover/project-actions:translate-x-0 group-hover/project-actions:opacity-100 translate-x-1">
                            <div className="group/action relative flex items-center">
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  const site = evaluationTargetById.get(row.id);
                                  if (site) {
                                    openEditEvaluationTargetModel(site);
                                  }
                                }}
                                aria-label="수정"
                                className={`project-list-icon-action inline-flex h-7 w-7 items-center justify-center rounded-full bg-transparent transition ${
                                  isDarkMode
                                    ? "text-white hover:bg-white/[0.075] hover:text-white"
                                    : "text-slate-700 hover:text-slate-900"
                                }`}
                              >
                                <Pencil size={14} />
                              </button>
                              <span
                                data-tooltip-tone={isDarkMode ? "dark" : "light"}
                                className={`project-table-tooltip invisible pointer-events-none absolute left-1/2 z-[9999] -translate-x-1/2 whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-medium group-hover/action:visible ${
                                  index === 0 ? "top-full mt-2" : "bottom-full mb-2"
                                }`}
                              >
                                수정
                              </span>
                            </div>
                            <div className="group/action relative flex items-center">
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  const site = evaluationTargetById.get(row.id);
                                  if (site) {
                                    openDeleteEvaluationTargetModel(site);
                                  }
                                }}
                                aria-label="제거"
                                className={`project-list-icon-action inline-flex h-7 w-7 items-center justify-center rounded-full bg-transparent transition ${
                                  isDarkMode
                                    ? "text-rose-400 hover:bg-white/[0.075] hover:text-rose-300"
                                    : "text-red-600 hover:text-red-700"
                                }`}
                              >
                                <Trash2 size={14} className={isDarkMode ? "text-rose-400" : "text-red-600"} />
                              </button>
                              <span
                                data-tooltip-tone={isDarkMode ? "dark" : "light"}
                                className={`project-table-tooltip invisible pointer-events-none absolute left-1/2 z-[9999] -translate-x-1/2 whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-medium group-hover/action:visible ${
                                  index === 0 ? "top-full mt-2" : "bottom-full mb-2"
                                }`}
                              >
                                제거
                              </span>
                            </div>
                          </div>
                          <div className="group/action relative flex h-7 w-7 items-center justify-center">
                            <button
                              type="button"
                              onClick={(event) => event.stopPropagation()}
                              className={`project-list-action inline-flex h-7 w-7 items-center justify-center rounded-full bg-transparent transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300 ${
                                isDarkMode ? "text-white" : "text-slate-700"
                              }`}
                              aria-label={`${row.name} 관리 메뉴`}
                            >
                              <MoreHorizontal size={14} />
                            </button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
              </table>
            </div>
          </div>
      </div>
      {editingEvaluationTargetModel
        ? createPortal(
            <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/55 px-4 py-6 backdrop-blur-sm">
              <div
                className="absolute inset-0"
                onClick={() => {
                  if (!isSavingEvaluationTarget) {
                    closeEditEvaluationTargetModel();
                  }
                }}
              />
              <article
                ref={editDialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="site-edit-title"
                aria-describedby="site-edit-description"
                tabIndex={-1}
                className={`relative z-10 w-full max-w-2xl rounded-2xl border p-5 ${
                  isDarkMode ? "border-[#23272f] bg-[#0C0E11]" : "border-slate-200 bg-white"
                }`}
              >
                <h3 id="site-edit-title" className={`text-lg font-semibold ${isDarkMode ? "text-white" : "text-slate-900"}`}>페이지 수정</h3>
                <p id="site-edit-description" className={`mt-1 text-sm ${isDarkMode ? "text-slate-400" : "text-slate-500"}`}>
                  페이지 이름과 주소를 수정할 수 있습니다.
                </p>

                {editEvaluationTargetError.length > 0 && (
                  <PanelMessage label={`페이지 수정 실패: ${editEvaluationTargetError}`} isError />
                )}

                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <label className="block sm:col-span-2">
                    <span className={`mb-1 block text-sm font-medium ${isDarkMode ? "text-slate-300" : "text-slate-700"}`}>페이지 이름</span>
                    <input
                      value={editSiteName}
                      onChange={(event) => setEditSiteName(event.target.value)}
                      className={`h-10 w-full rounded-lg border px-3 text-sm outline-none ${
                        isDarkMode
                          ? "border-[#23272f] bg-[#11141a] text-white placeholder:text-slate-500 focus:border-slate-500"
                          : "border-slate-200 text-slate-900 placeholder:text-slate-400 focus:border-slate-400"
                      }`}
                      placeholder="예: 방문 안내"
                    />
                  </label>

                  <label className="block sm:col-span-2">
                    <span className={`mb-1 block text-sm font-medium ${isDarkMode ? "text-slate-300" : "text-slate-700"}`}>기본 주소</span>
                    <input
                      value={editSiteBaseUrl}
                      onChange={(event) => setEditSiteBaseUrl(event.target.value)}
                      className={`h-10 w-full rounded-lg border px-3 text-sm outline-none ${
                        isDarkMode
                          ? "border-[#23272f] bg-[#11141a] text-white placeholder:text-slate-500 focus:border-slate-500"
                          : "border-slate-200 text-slate-900 placeholder:text-slate-400 focus:border-slate-400"
                      }`}
                      placeholder="https://example.com"
                    />
                  </label>

                </div>

                <div className="mt-5 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    disabled={isSavingEvaluationTarget}
                    onClick={closeEditEvaluationTargetModel}
                    className={`inline-flex h-9 items-center rounded-lg px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 ${
                      isDarkMode
                        ? "bg-slate-900 font-semibold text-white hover:bg-slate-800"
                        : "border border-slate-200 bg-white font-medium text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    취소
                  </button>
                  <button
                    type="button"
                    disabled={isSavingEvaluationTarget}
                    onClick={() => {
                      void handleSaveEvaluationTargetModel();
                    }}
                    className={`inline-flex h-9 items-center rounded-lg px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 ${
                      isDarkMode
                        ? "border border-slate-200 bg-white font-medium text-slate-700 hover:bg-slate-50"
                        : "bg-slate-900 font-semibold text-white hover:bg-slate-800"
                    }`}
                  >
                    {isSavingEvaluationTarget ? "저장 중..." : "저장"}
                  </button>
                </div>
              </article>
            </div>,
            document.body
          )
        : null}
      {deletingEvaluationTargetModel
        ? createPortal(
            <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/55 px-4 py-6 backdrop-blur-sm">
              <div
                className="absolute inset-0"
                onClick={() => {
                  if (!isDeletingEvaluationTarget) {
                    closeDeleteEvaluationTargetModel();
                  }
                }}
              />
              <article
                ref={deleteDialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="site-delete-title"
                aria-describedby="site-delete-description"
                tabIndex={-1}
                className={`relative z-10 w-full max-w-md rounded-2xl border p-5 ${
                  isDarkMode ? "border-[#23272f] bg-[#0C0E11]" : "border-slate-200 bg-white"
                }`}
              >
                <h3 id="site-delete-title" className={`text-lg font-semibold ${isDarkMode ? "text-white" : "text-slate-900"}`}>페이지 제거</h3>
                <p id="site-delete-description" className={`mt-2 text-sm ${isDarkMode ? "text-slate-400" : "text-slate-500"}`}>
                  <span className={isDarkMode ? "font-medium text-white" : "font-medium text-slate-700"}>
                    {deletingEvaluationTargetModel.name}
                  </span>
                  {" "}페이지를 제거하시겠습니까?
                </p>

                {deleteEvaluationTargetError.length > 0 && (
                  <PanelMessage label={`페이지 제거 실패: ${deleteEvaluationTargetError}`} isError />
                )}

                <div className="mt-5 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    disabled={isDeletingEvaluationTarget}
                    onClick={closeDeleteEvaluationTargetModel}
                    className={`inline-flex h-9 items-center rounded-lg px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 ${
                      isDarkMode
                        ? "bg-slate-900 font-semibold text-white hover:bg-slate-800"
                        : "border border-slate-200 bg-white font-medium text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    아니요
                  </button>
                  <button
                    type="button"
                    disabled={isDeletingEvaluationTarget}
                    onClick={() => {
                      void handleConfirmDeleteEvaluationTargetModel();
                    }}
                    className="inline-flex h-9 items-center rounded-lg bg-rose-600 px-3 text-sm font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isDeletingEvaluationTarget ? "제거 중..." : "네"}
                  </button>
                </div>
              </article>
            </div>,
            document.body
          )
        : null}
    </div>
  );
}
