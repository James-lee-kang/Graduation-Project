import { RefreshCw } from "lucide-react";
import { formatDateTime } from "@/components/dashboard/shared/utils";

export function PageAnalysisActions({ analyzedAt, isRequestingAnalysis, onRequestAnalysis, analysisRequestError, outdatedIssueCount = 0 }: {
  analyzedAt: string | null;
  /** Findings whose stored location no longer matches the current page. */
  outdatedIssueCount?: number;
  isRequestingAnalysis: boolean;
  onRequestAnalysis?: () => void;
  analysisRequestError: string | null;
}) {
  return (
    <div className="site-page-analysis-actions">
      <dl className="site-page-analysis-actions__metadata">
        <div>
          <dt className="sr-only">최근 분석</dt>
          <dd>{formatDateTime(analyzedAt)}</dd>
        </div>
      </dl>
      {outdatedIssueCount > 0 && (
        <p className="site-page-analysis-actions__stale" role="status">
          분석 이후 페이지가 바뀜<span className="sr-only">
            . 문제 {outdatedIssueCount.toLocaleString("ko-KR")}건의 위치가 현재 페이지와 맞지 않습니다. 재분석하면 최신 결과를 볼 수 있습니다.</span>
        </p>
      )}
      {onRequestAnalysis && (
        <button type="button" className="site-page-analysis-actions__rescan"
          onClick={onRequestAnalysis} disabled={isRequestingAnalysis} aria-busy={isRequestingAnalysis}
          aria-describedby={analysisRequestError ? "site-analysis-request-error" : undefined}>
          <RefreshCw size={12} aria-hidden="true" />
          {isRequestingAnalysis ? "요청 중…" : "재분석"}
        </button>
      )}
    </div>
  );
}
