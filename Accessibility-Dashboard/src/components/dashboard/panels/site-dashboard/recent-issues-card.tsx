import { useEffect, useMemo, useState } from "react";

import type { RecentIssueRow } from "./types";

type RecentIssuesCardProps = {
  rows: RecentIssueRow[];
};

export function RecentIssuesCard({ rows }: RecentIssuesCardProps) {
  const [activePageIndex, setActivePageIndex] = useState(0);
  const pageSize = 2;
  const pageCount = Math.max(Math.ceil(rows.length / pageSize), 1);
  const canMoveBackward = activePageIndex > 0;
  const canMoveForward = activePageIndex < pageCount - 1;
  const visibleRows = useMemo(
    () => rows.slice(activePageIndex * pageSize, activePageIndex * pageSize + pageSize),
    [activePageIndex, rows]
  );

  useEffect(() => {
    setActivePageIndex((current) => Math.min(current, pageCount - 1));
  }, [pageCount]);

  return (
    <article className="dashboard-card site-recent-issues-card flex h-full min-h-[440px] flex-col rounded-xl border border-slate-200 bg-slate-100 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-slate-900">최근 발견 이슈</h2>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {pageCount > 1 && (
            <nav className="flex items-center gap-1" aria-label="Recent issue navigation">
              <button
                type="button"
                aria-label="Previous recent issues"
                disabled={!canMoveBackward}
                className="site-recent-issue-nav-button inline-flex h-7 w-7 items-center justify-center rounded-full bg-transparent text-slate-500 transition hover:bg-slate-200/80 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
                onClick={() => setActivePageIndex((current) => Math.max(current - 1, 0))}
              >
                <svg width="28" height="28" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                  <path
                    d="M22.499 12.85a.9.9 0 0 1 .57.205l.067.06a.9.9 0 0 1 .06 1.206l-.06.066-5.585 5.586-.028.027.028.027 5.585 5.587a.9.9 0 0 1 .06 1.207l-.06.066a.9.9 0 0 1-1.207.06l-.066-.06-6.25-6.25a1 1 0 0 1-.158-.212l-.038-.08a.9.9 0 0 1-.03-.606l.03-.083a1 1 0 0 1 .137-.226l.06-.066 6.25-6.25a.9.9 0 0 1 .635-.263Z"
                    fill="currentColor"
                    stroke="currentColor"
                    strokeWidth=".078"
                  />
                </svg>
              </button>
              <button
                type="button"
                aria-label="Next recent issues"
                disabled={!canMoveForward}
                className="site-recent-issue-nav-button inline-flex h-7 w-7 items-center justify-center rounded-full bg-transparent text-slate-500 transition hover:bg-slate-200/80 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
                onClick={() => setActivePageIndex((current) => Math.min(current + 1, pageCount - 1))}
              >
                <svg className="rotate-180" width="28" height="28" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                  <path
                    d="M22.499 12.85a.9.9 0 0 1 .57.205l.067.06a.9.9 0 0 1 .06 1.206l-.06.066-5.585 5.586-.028.027.028.027 5.585 5.587a.9.9 0 0 1 .06 1.207l-.06.066a.9.9 0 0 1-1.207.06l-.066-.06-6.25-6.25a1 1 0 0 1-.158-.212l-.038-.08a.9.9 0 0 1-.03-.606l.03-.083a1 1 0 0 1 .137-.226l.06-.066 6.25-6.25a.9.9 0 0 1 .635-.263Z"
                    fill="currentColor"
                    stroke="currentColor"
                    strokeWidth=".078"
                  />
                </svg>
              </button>
            </nav>
          )}
        <p className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-[#8a94a6]">
          총
          <span className="text-sm font-bold text-slate-950">{rows.length}건</span>
        </p>
      </div>

      </div>

      <div className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1">
        {rows.length === 0 ? (
          <div className="flex h-full items-center justify-center rounded-2xl bg-white px-4 text-center text-sm font-medium text-slate-500">
            표시할 이슈가 없습니다.
          </div>
        ) : (
          <div className="space-y-2">
            {visibleRows.map(({ analyzerLabel, issue, issueGuides, severity }) => (
              <div key={issue.id} className="rounded-2xl bg-white px-3 py-3">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span
                    className="shrink-0 rounded-full px-2 py-1 text-[10px] font-bold text-white"
                    style={{ backgroundColor: severity.color }}
                  >
                    {severity.label}
                  </span>
                  <span className="site-recent-issue-kwcag-tag truncate rounded-full bg-slate-950 px-2 py-1 text-[11px] font-bold text-white">
                    KWCAG {issue.issueCode}
                  </span>
                  <span className="truncate rounded-full border border-slate-200 bg-white px-2 py-1 text-[11px] font-bold text-slate-600">
                    {analyzerLabel}
                  </span>
                </div>
                <p className="mt-2 truncate text-sm font-bold text-slate-950" title={issue.issueTitle}>
                  {issue.issueTitle}
                </p>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">{issue.message}</p>
                {issue.locationPath && (
                  <div className="site-recent-issue-detail-box mt-2 rounded-lg bg-[#f3f3f3] px-2 py-2">
                    <p className="text-[10px] font-bold text-slate-400">문제 위치</p>
                    <p className="mt-1 truncate font-mono text-[11px] leading-4 text-slate-600" title={issue.locationPath}>
                      {issue.locationPath}
                    </p>
                  </div>
                )}
                <div className="site-recent-issue-detail-box mt-3 rounded-xl bg-[#f3f3f3] px-3 py-3">
                  <div className="flex min-w-0 items-center justify-between gap-3">
                    <p className="shrink-0 text-[11px] font-bold text-[#ef6a50]">AI 가이드</p>
                  </div>
                  {issueGuides.length === 0 ? (
                    <>
                      <p className="mt-2 text-xs font-bold text-slate-900">
                        {issue.recommendation ? "개선 권장사항" : "개선 가이드 준비 중"}
                      </p>
                      <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">
                        {issue.recommendation ?? "이슈 위치와 컴포넌트 역할을 확인한 뒤 WCAG 기준에 맞는 수정안을 연결해 주세요."}
                      </p>
                    </>
                  ) : (
                    <div className="mt-2 space-y-2">
                      {issueGuides.map((guide) => (
                        <div key={guide.id} className="rounded-lg bg-white px-2 py-2">
                          <p className="text-xs font-bold text-slate-900">{guide.title}</p>
                          <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600">{guide.guideContent}</p>
                          {guide.recommendation && (
                            <p className="mt-2 text-[11px] font-medium leading-4 text-slate-600">{guide.recommendation}</p>
                          )}
                          {guide.exampleCode && (
                            <pre className="mt-2 max-h-16 overflow-auto rounded-lg bg-slate-950 px-2 py-2 text-[10px] leading-4 text-white">
                              <code>{guide.exampleCode}</code>
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}
