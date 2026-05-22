import { createPortal } from "react-dom";

import { PanelMessage } from "../shared/display";
import { useDialogAccessibility } from "../shared/use-dialog-accessibility";

export function OrganizationModelCreateModal({
  isOpen,
  isDarkMode,
  name,
  description,
  isSubmitting,
  errorMessage,
  onNameChange,
  onDescriptionChange,
  onClose,
  onSubmit
}: {
  isOpen: boolean;
  isDarkMode: boolean;
  name: string;
  description: string;
  isSubmitting: boolean;
  errorMessage: string;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onClose: () => void;
  onSubmit: () => Promise<void>;
}) {
  const dialogRef = useDialogAccessibility({
    isOpen,
    onClose,
    closeDisabled: isSubmitting
  });

  if (!isOpen) {
    return null;
  }

  return createPortal(
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/55 px-4 py-6 backdrop-blur-sm">
      <div className="absolute inset-0" onClick={onClose} />
      <article
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="organization-create-title"
        aria-describedby="organization-create-description"
        tabIndex={-1}
        className={`relative z-10 w-full max-w-xl rounded-2xl border p-5 ${
          isDarkMode ? "border-[#23272f] bg-[#0C0E11]" : "border-slate-200 bg-white"
        }`}
      >
        <h3 id="organization-create-title" className={`text-lg font-semibold ${isDarkMode ? "text-white" : "text-slate-900"}`}>프로젝트 추가</h3>
        <p id="organization-create-description" className={`mt-1 text-sm ${isDarkMode ? "text-slate-400" : "text-slate-500"}`}>이름과 설명을 입력해 새 프로젝트를 만듭니다.</p>

        {errorMessage.length > 0 && <PanelMessage label={`프로젝트 생성 실패: ${errorMessage}`} isError />}

        <div className="mt-4 space-y-4">
          <label className="block">
            <span className={`mb-1 block text-sm font-semibold ${isDarkMode ? "text-slate-300" : "text-slate-700"}`}>프로젝트 이름</span>
            <input
              value={name}
              onChange={(event) => onNameChange(event.target.value)}
              className={`h-10 w-full rounded-lg border px-3 text-sm outline-none ${
                isDarkMode
                  ? "border-[#23272f] bg-[#11141a] text-white placeholder:text-slate-500 focus:border-slate-500"
                  : "border-slate-200 text-slate-900 placeholder:text-slate-400 focus:border-slate-400"
              }`}
              placeholder="예: 고령자 접근성 포털"
            />
          </label>

          <label className="block">
            <span className={`mb-1 block text-sm font-semibold ${isDarkMode ? "text-slate-300" : "text-slate-700"}`}>설명</span>
            <textarea
              value={description}
              onChange={(event) => onDescriptionChange(event.target.value)}
              className={`min-h-28 w-full rounded-lg border px-3 py-2 text-sm outline-none ${
                isDarkMode
                  ? "border-[#23272f] bg-[#11141a] text-white placeholder:text-slate-500 focus:border-slate-500"
                  : "border-slate-200 text-slate-900 placeholder:text-slate-400 focus:border-slate-400"
              }`}
              placeholder="프로젝트 목적과 범위를 입력하세요"
            />
          </label>
        </div>

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={onClose}
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
            disabled={isSubmitting}
            onClick={() => {
              void onSubmit();
            }}
            className={`inline-flex h-9 items-center rounded-lg px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 ${
              isDarkMode
                ? "border border-transparent bg-[#ef6a50] font-semibold text-white hover:bg-[#e85d43]"
                : "bg-[#ef6a50] font-semibold text-white hover:bg-[#e85d43]"
            }`}
          >
            {isSubmitting ? "생성 중..." : "생성"}
          </button>
        </div>
      </article>
    </div>,
    document.body
  );
}
