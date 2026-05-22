import { useEffect, useState } from "react";

import { getApiErrorMessage } from "@/services/backend-api";
import type {
  CreateEvaluationTargetInput as CreateEvaluationTargetModelInput,
  OrganizationModel
} from "@/types/accessibility-domain";

import { useDialogAccessibility } from "../shared/use-dialog-accessibility";

export function SiteCreateModal({
  isOpen,
  project,
  onAddEvaluationTargetModel,
  onClose
}: {
  isOpen: boolean;
  isDarkMode: boolean;
  project: OrganizationModel;
  onAddEvaluationTargetModel: (input: CreateEvaluationTargetModelInput) => Promise<void>;
  onClose: () => void;
}) {
  const [siteName, setSiteName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [isSubmittingSite, setIsSubmittingSite] = useState(false);
  const [siteCreateError, setSiteCreateError] = useState("");
  const dialogRef = useDialogAccessibility({
    isOpen,
    onClose,
    closeDisabled: isSubmittingSite
  });

  useEffect(() => {
    if (!isOpen) {
      setSiteName("");
      setBaseUrl("");
      setSiteCreateError("");
    }
  }, [isOpen]);

  const handleAddSite = async () => {
    const name = siteName.trim();
    const accessUrl = baseUrl.trim();

    if (name.length === 0 || accessUrl.length === 0) {
      setSiteCreateError("페이지 이름과 주소는 필수입니다.");
      return;
    }

    setIsSubmittingSite(true);
    setSiteCreateError("");

    try {
      await onAddEvaluationTargetModel({
        projectId: project.id,
        name,
        accessUrl
      });

      setSiteName("");
      setBaseUrl("");
      onClose();
    } catch (error) {
      setSiteCreateError(getApiErrorMessage(error, "페이지 추가 중 오류가 발생했습니다."));
    } finally {
      setIsSubmittingSite(false);
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/55 px-4 py-6 backdrop-blur-sm">
      <div
        className="absolute inset-0"
        onClick={() => {
          if (!isSubmittingSite) {
            onClose();
          }
        }}
      />

      <article
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="site-create-title"
        aria-describedby="site-create-description"
        tabIndex={-1}
        className="relative w-full max-w-4xl rounded-[28px] border border-slate-200 bg-white p-6 shadow-[0_20px_80px_rgba(15,23,42,0.22)]"
      >
        <div className="mb-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">페이지 추가</p>
            <h2 id="site-create-title" className="mt-1 text-2xl font-bold text-slate-900">{project.name}</h2>
            <p id="site-create-description" className="mt-2 text-sm text-slate-500">분석할 페이지 정보를 입력합니다.</p>
          </div>
        </div>

        <div className="space-y-5">
          <div>
            <p className="text-sm font-semibold text-slate-900">분석 페이지 정보</p>
            <p className="mt-1 text-xs text-slate-500">페이지 이름과 주소를 입력하면 프로젝트에 분석 대상 페이지가 추가됩니다.</p>
          </div>

          {siteCreateError.length > 0 && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
              페이지 추가 실패: {siteCreateError}
            </div>
          )}

          <div className="grid gap-4">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-700">페이지 이름</span>
              <input
                value={siteName}
                onChange={(event) => setSiteName(event.target.value)}
                placeholder="예: 시청 대표 포털 메인"
                className="h-11 w-full rounded-xl border border-slate-200 px-3 text-sm text-slate-900 outline-none focus:border-slate-400"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-700">페이지 주소</span>
              <input
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder="https://example.com"
                className="h-11 w-full rounded-xl border border-slate-200 px-3 text-sm text-slate-900 outline-none focus:border-slate-400"
              />
            </label>
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            disabled={isSubmittingSite}
            onClick={onClose}
            className="site-modal-footer-cancel inline-flex h-10 items-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            취소
          </button>

          <button
            type="button"
            disabled={isSubmittingSite}
            onClick={() => {
              void handleAddSite();
            }}
            className="site-modal-footer-submit inline-flex h-10 items-center rounded-xl border border-transparent bg-[#ef6a50] px-4 text-sm font-semibold text-white hover:bg-[#e85d43] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmittingSite ? "분석 시작 중..." : "분석 시작"}
          </button>
        </div>
      </article>
    </div>
  );
}
