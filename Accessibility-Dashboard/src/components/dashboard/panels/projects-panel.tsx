import { ArrowDown, ArrowUp, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { createPortal } from "react-dom";

import { getApiErrorMessage } from "@/services/backend-api";
import type { OrganizationModel } from "@/types/accessibility-domain";

import { PanelMessage } from "../shared/display";
import { useDialogAccessibility } from "../shared/use-dialog-accessibility";
import { formatDateTime } from "../shared/utils";

export function OrganizationModelsPanel({
  organizations,
  isLoading,
  errorMessage,
  isDarkMode,
  onUpdateOrganizationModel,
  onDeleteOrganizationModel,
  onOrganizationModelClick
}: {
  organizations: OrganizationModel[];
  isLoading: boolean;
  errorMessage: string;
  isDarkMode: boolean;
  onUpdateOrganizationModel: (input: { projectId: number; name: string; description: string }) => Promise<void>;
  onDeleteOrganizationModel: (projectId: number) => Promise<void>;
  onOrganizationModelClick: (projectId: number) => void;
}) {
  const [sortConfig, setSortConfig] = useState<{
    key: "name" | "targetSites" | "updatedAt";
    direction: "asc" | "desc";
  }>({
    key: "updatedAt",
    direction: "desc"
  });
  const [editingOrganizationModel, setEditingOrganizationModel] = useState<OrganizationModel | null>(null);
  const [editOrganizationModelName, setEditOrganizationModelName] = useState("");
  const [editOrganizationModelDescription, setEditOrganizationModelDescription] = useState("");
  const [editOrganizationModelError, setEditOrganizationModelError] = useState("");
  const [isSavingOrganizationModel, setIsSavingOrganizationModel] = useState(false);
  const [deletingOrganizationModel, setDeletingOrganizationModel] = useState<OrganizationModel | null>(null);
  const [deleteOrganizationModelError, setDeleteOrganizationModelError] = useState("");
  const [isDeletingOrganizationModel, setIsDeletingOrganizationModel] = useState(false);

  const closeEditOrganizationModel = () => {
    if (isSavingOrganizationModel) {
      return;
    }
    setEditingOrganizationModel(null);
    setEditOrganizationModelError("");
  };
  const closeDeleteOrganizationModel = () => {
    if (isDeletingOrganizationModel) {
      return;
    }
    setDeletingOrganizationModel(null);
    setDeleteOrganizationModelError("");
  };
  const editDialogRef = useDialogAccessibility({
    isOpen: editingOrganizationModel !== null,
    onClose: closeEditOrganizationModel,
    closeDisabled: isSavingOrganizationModel
  });
  const deleteDialogRef = useDialogAccessibility({
    isOpen: deletingOrganizationModel !== null,
    onClose: closeDeleteOrganizationModel,
    closeDisabled: isDeletingOrganizationModel
  });

  if (isLoading) {
    return <PanelMessage label="프로젝트 데이터를 불러오는 중..." />;
  }

  if (errorMessage.length > 0) {
    return <PanelMessage label={`프로젝트 로드 실패: ${errorMessage}`} isError />;
  }

  const organizationsWithLastUpdated = [...organizations]
    .map((organization) => {
      const latestEvaluationTargetModelAt = organization.evaluationTargets.reduce((latest, site) => {
        const timestamp = Date.parse(site.createdAt);
        return Number.isNaN(timestamp) ? latest : Math.max(latest, timestamp);
      }, 0);
      const projectUpdatedAt = Date.parse(organization.updatedAt);
      const lastUpdatedAt = Math.max(Number.isNaN(projectUpdatedAt) ? 0 : projectUpdatedAt, latestEvaluationTargetModelAt);

      return {
        ...organization,
        lastUpdatedAt: lastUpdatedAt > 0 ? new Date(lastUpdatedAt).toISOString() : organization.updatedAt
      };
    });

  const sortedOrganizationModels = [...organizationsWithLastUpdated].sort((a, b) => {
    const updatedDiff = Date.parse(b.lastUpdatedAt) - Date.parse(a.lastUpdatedAt);

    if (sortConfig.key === "name") {
      const nameDiff = a.name.localeCompare(b.name, "ko");
      if (nameDiff !== 0) {
        return sortConfig.direction === "asc" ? nameDiff : -nameDiff;
      }
      return sortConfig.direction === "asc" ? updatedDiff : -updatedDiff;
    }

    if (sortConfig.key === "targetSites") {
      const siteCountDiff = b.evaluationTargets.length - a.evaluationTargets.length;
      if (siteCountDiff !== 0) {
        return sortConfig.direction === "desc" ? siteCountDiff : -siteCountDiff;
      }
      return sortConfig.direction === "desc" ? updatedDiff : -updatedDiff;
    }

    return sortConfig.direction === "desc" ? updatedDiff : -updatedDiff;
  });

  const handleSort = (key: "name" | "targetSites" | "updatedAt") => {
    setSortConfig((current) => {
      if (current.key === key) {
        return {
          key,
          direction: current.direction === "asc" ? "desc" : "asc"
        };
      }

      return {
        key,
        direction: key === "name" ? "asc" : "desc"
      };
    });
  };

  const getSortIndicator = (key: "name" | "targetSites" | "updatedAt") => {
    if (sortConfig.key !== key) {
      return null;
    }

    return (
      <span className="inline-flex h-4 w-3 shrink-0 items-center justify-center leading-none">
        {sortConfig.direction === "asc" ? (
          <ArrowUp size={11} strokeWidth={2.4} className="block" />
        ) : (
          <ArrowDown size={11} strokeWidth={2.4} className="block" />
        )}
      </span>
    );
  };

  const openEditOrganizationModel = (organization: OrganizationModel) => {
    setEditingOrganizationModel(organization);
    setEditOrganizationModelName(organization.name);
    setEditOrganizationModelDescription(organization.description);
    setEditOrganizationModelError("");
  };

  const openDeleteOrganizationModel = (organization: OrganizationModel) => {
    setDeletingOrganizationModel(organization);
    setDeleteOrganizationModelError("");
  };

  const handleSaveOrganizationModel = async () => {
    if (!editingOrganizationModel) {
      return;
    }

    const name = editOrganizationModelName.trim();
    const description = editOrganizationModelDescription.trim();

    if (name.length === 0) {
      setEditOrganizationModelError("프로젝트 이름은 필수입니다.");
      return;
    }

    setIsSavingOrganizationModel(true);
    setEditOrganizationModelError("");

    try {
      await onUpdateOrganizationModel({
        projectId: editingOrganizationModel.id,
        name,
        description
      });
      setEditingOrganizationModel(null);
      setEditOrganizationModelName("");
      setEditOrganizationModelDescription("");
    } catch (error) {
      setEditOrganizationModelError(getApiErrorMessage(error, "프로젝트 수정 중 오류가 발생했습니다."));
    } finally {
      setIsSavingOrganizationModel(false);
    }
  };

  const handleConfirmDeleteOrganizationModel = async () => {
    if (!deletingOrganizationModel) {
      return;
    }

    setIsDeletingOrganizationModel(true);
    setDeleteOrganizationModelError("");

    try {
      await onDeleteOrganizationModel(deletingOrganizationModel.id);
      setDeletingOrganizationModel(null);
    } catch (error) {
      setDeleteOrganizationModelError(getApiErrorMessage(error, "프로젝트 제거 중 오류가 발생했습니다."));
    } finally {
      setIsDeletingOrganizationModel(false);
    }
  };

  return (
    <div className="-mt-2 space-y-0">
      {organizations.length === 0 ? (
        <PanelMessage label="등록된 프로젝트가 없습니다." />
      ) : (
        <div className="project-list-table overflow-visible bg-transparent">
          <div className="overflow-x-auto">
            <table className="w-full table-fixed text-left">
              <colgroup>
                <col className="w-[24%]" />
                <col className="w-[44%]" />
                <col className="w-[12%]" />
                <col className="w-[18%]" />
                <col className="w-[6%]" />
              </colgroup>
              <thead className="project-list-head border-b border-slate-200/80 text-xs text-slate-500">
                <tr>
                  <th className="h-8 py-0 font-medium align-middle">
                    <button type="button" onClick={() => handleSort("name")} className="flex h-8 w-full items-center gap-0.5 px-4 text-left cursor-pointer select-none">
                      프로젝트 이름
                      {getSortIndicator("name")}
                    </button>
                  </th>
                  <th className="h-8 px-4 py-0 font-medium align-middle">설명</th>
                  <th className="h-8 py-0 font-medium align-middle">
                    <button type="button" onClick={() => handleSort("targetSites")} className="flex h-8 w-full items-center gap-0.5 px-4 text-left cursor-pointer select-none">
                      대상 페이지
                      {getSortIndicator("targetSites")}
                    </button>
                  </th>
                  <th className="h-8 py-0 font-medium align-middle">
                    <button type="button" onClick={() => handleSort("updatedAt")} className="flex h-8 w-full items-center gap-0.5 px-4 text-left cursor-pointer select-none">
                      최근 수정
                      {getSortIndicator("updatedAt")}
                    </button>
                  </th>
                  <th className="h-8 px-4 py-0 align-middle" aria-label="프로젝트 액션" />
                </tr>
              </thead>
              <tbody>
                {sortedOrganizationModels.map((project, index) => (
                  <tr
                    key={project.id}
                    onClick={() => onOrganizationModelClick(project.id)}
                    className={`project-list-row group cursor-pointer ${index !== sortedOrganizationModels.length - 1 ? "border-b border-slate-200/80" : ""}`}
                  >
                    <td className="px-4 py-1.5 align-middle">
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold text-slate-900">{project.name}</p>
                      </div>
                    </td>
                    <td className="px-4 py-1.5 align-middle">
                      <p className="truncate text-xs leading-4 text-slate-600">
                        {project.description || "설명이 없습니다."}
                      </p>
                    </td>
                    <td className="px-4 py-1.5 align-middle">
                      <span className="text-xs font-medium text-slate-700">
                        {project.evaluationTargets.length}개
                      </span>
                    </td>
                    <td className="project-list-updated px-4 py-1.5 align-middle text-xs tabular-nums text-slate-500">
                      {formatDateTime(project.lastUpdatedAt)}
                    </td>
                    <td className="relative px-4 py-1.5 text-right align-middle">
                      <div className="group/project-actions absolute right-4 top-1/2 flex h-9 w-[106px] -translate-y-1/2 items-center justify-end">
                        <div
                          className="pointer-events-none absolute right-9 top-1/2 inline-flex h-9 w-[68px] -translate-y-1/2 items-center justify-end gap-1 opacity-0 transition-all duration-200 ease-out group-hover/project-actions:pointer-events-auto group-hover/project-actions:opacity-100 group-hover/project-actions:translate-x-0 translate-x-1"
                        >
                          <div className="group/action relative flex items-center">
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                openEditOrganizationModel(project);
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
                                openDeleteOrganizationModel(project);
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
                            aria-label={`${project.name} 관리 메뉴`}
                          >
                            <MoreHorizontal size={14} />
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {editingOrganizationModel
        ? createPortal(
            <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/55 px-4 py-6 backdrop-blur-sm">
              <div
                className="absolute inset-0"
                onClick={closeEditOrganizationModel}
              />
              <article
                ref={editDialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="project-edit-title"
                aria-describedby="project-edit-description"
                tabIndex={-1}
                className={`relative z-10 w-full max-w-xl rounded-2xl border p-5 ${
                  isDarkMode ? "border-[#23272f] bg-[#0C0E11]" : "border-slate-200 bg-white"
                }`}
              >
                <h3 id="project-edit-title" className={`text-lg font-semibold ${isDarkMode ? "text-white" : "text-slate-900"}`}>프로젝트 수정</h3>
                <p id="project-edit-description" className={`mt-1 text-sm ${isDarkMode ? "text-slate-400" : "text-slate-500"}`}>프로젝트 이름과 설명을 수정할 수 있습니다.</p>

                {editOrganizationModelError.length > 0 && (
                  <PanelMessage label={`프로젝트 수정 실패: ${editOrganizationModelError}`} isError />
                )}

                <div className="mt-4 space-y-4">
                  <label className="block">
                    <span className={`mb-1 block text-sm font-semibold ${isDarkMode ? "text-slate-300" : "text-slate-700"}`}>프로젝트 이름</span>
                    <input
                      value={editOrganizationModelName}
                      onChange={(event) => setEditOrganizationModelName(event.target.value)}
                      className={`h-10 w-full rounded-lg border px-3 text-sm outline-none ${
                        isDarkMode
                          ? "border-[#23272f] bg-[#11141a] text-white placeholder:text-slate-500 focus:border-slate-500"
                          : "border-slate-200 text-slate-900 placeholder:text-slate-400 focus:border-slate-400"
                      }`}
                      placeholder="예: 고령자 접근성 점검"
                    />
                  </label>

                  <label className="block">
                    <span className={`mb-1 block text-sm font-semibold ${isDarkMode ? "text-slate-300" : "text-slate-700"}`}>설명</span>
                    <textarea
                      value={editOrganizationModelDescription}
                      onChange={(event) => setEditOrganizationModelDescription(event.target.value)}
                      className={`min-h-28 w-full rounded-lg border px-3 py-2 text-sm outline-none ${
                        isDarkMode
                          ? "border-[#23272f] bg-[#11141a] text-white placeholder:text-slate-500 focus:border-slate-500"
                          : "border-slate-200 text-slate-900 placeholder:text-slate-400 focus:border-slate-400"
                      }`}
                      placeholder="프로젝트 목적과 범위를 입력하세요."
                    />
                  </label>
                </div>

                <div className="mt-5 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    disabled={isSavingOrganizationModel}
                    onClick={closeEditOrganizationModel}
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
                    disabled={isSavingOrganizationModel}
                    onClick={() => {
                      void handleSaveOrganizationModel();
                    }}
                      className={`inline-flex h-9 items-center rounded-lg px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 ${
                        isDarkMode
                          ? "border border-transparent bg-[#ef6a50] font-semibold text-white hover:bg-[#e85d43]"
                          : "bg-[#ef6a50] font-semibold text-white hover:bg-[#e85d43]"
                      }`}
                  >
                    {isSavingOrganizationModel ? "저장 중..." : "저장"}
                  </button>
                </div>
              </article>
            </div>,
            document.body
          )
        : null}
      {deletingOrganizationModel
        ? createPortal(
            <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/55 px-4 py-6 backdrop-blur-sm">
              <div
                className="absolute inset-0"
                onClick={closeDeleteOrganizationModel}
              />
              <article
                ref={deleteDialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="project-delete-title"
                aria-describedby="project-delete-description"
                tabIndex={-1}
                className={`relative z-10 w-full max-w-md rounded-2xl border p-5 ${
                  isDarkMode ? "border-[#23272f] bg-[#0C0E11]" : "border-slate-200 bg-white"
                }`}
              >
                <h3 id="project-delete-title" className={`text-lg font-semibold ${isDarkMode ? "text-white" : "text-slate-900"}`}>프로젝트 제거</h3>
                <p id="project-delete-description" className={`mt-2 text-sm ${isDarkMode ? "text-slate-400" : "text-slate-500"}`}>
                  <span className={`font-medium ${isDarkMode ? "text-slate-200" : "text-slate-700"}`}>{deletingOrganizationModel.name}</span> 프로젝트를 제거하시겠습니까?
                </p>

                {deleteOrganizationModelError.length > 0 && (
                  <PanelMessage label={`프로젝트 제거 실패: ${deleteOrganizationModelError}`} isError />
                )}

                <div className="mt-5 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    disabled={isDeletingOrganizationModel}
                    onClick={closeDeleteOrganizationModel}
                    className={`inline-flex h-9 items-center rounded-lg border px-3 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60 ${
                      isDarkMode
                        ? "border-[#23272f] bg-slate-900 text-slate-200 hover:bg-slate-800"
                        : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    아니요
                  </button>
                  <button
                    type="button"
                    disabled={isDeletingOrganizationModel}
                    onClick={() => {
                      void handleConfirmDeleteOrganizationModel();
                    }}
                    className="inline-flex h-9 items-center rounded-lg bg-rose-600 px-3 text-sm font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isDeletingOrganizationModel ? "제거 중..." : "네"}
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

