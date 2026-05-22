import type {
  AnalysisResult,
  EvaluationRequestModel,
  EvaluationTargetModel,
  ImprovementGuide,
  IssueResultModel,
  OrganizationModel,
  ScoreResult
} from "@/types/accessibility-domain";

import { getScoreGrade } from "../shared/score-utils";
import { fallbackWcagCriterion, severityChartItems, wcagCriterionByIssueCode } from "./site-dashboard/constants";
import { RecentIssuesCard } from "./site-dashboard/recent-issues-card";
import { ScoreTrendCard } from "./site-dashboard/score-trend-card";
import type { RecentIssueRow, ScoreChartItem, SiteSummaryItem } from "./site-dashboard/types";
import { formatDateKey, formatDateLabel, formatShortDate, getAnalyzerTypeLabel, normalizeChartData } from "./site-dashboard/utils";

type SiteDashboardPanelProps = {
  organization: OrganizationModel;
  evaluationTarget: EvaluationTargetModel;
  evaluationRequests: EvaluationRequestModel[];
  analysisResults: AnalysisResult[];
  scoreResults: ScoreResult[];
  issueResults: IssueResultModel[];
  improvementGuides: ImprovementGuide[];
};

export function SiteDashboardPanel(props: SiteDashboardPanelProps) {
  const { evaluationTarget, evaluationRequests, analysisResults, improvementGuides, issueResults, scoreResults } = props;
  const targetEvaluationRequests = evaluationRequests.filter((request) => request.evaluationTargetId === evaluationTarget.id);
  const scoreByRequestId = new Map(scoreResults.map((scoreResult) => [scoreResult.evaluationRequestId, scoreResult]));
  const requestIdByAnalysisResultId = new Map(
    analysisResults.map((analysisResult) => [analysisResult.id, analysisResult.evaluationRequestId])
  );
  const analysisResultById = new Map(analysisResults.map((analysisResult) => [analysisResult.id, analysisResult]));
  const issueCountByRequestId = new Map<number, number>();
  const guidesByIssueId = buildGuidesByIssueId(improvementGuides);

  for (const issue of issueResults) {
    const requestId = requestIdByAnalysisResultId.get(issue.analysisResultId);
    if (requestId === undefined) {
      continue;
    }

    issueCountByRequestId.set(requestId, (issueCountByRequestId.get(requestId) ?? 0) + 1);
  }

  const completedScoreItems = targetEvaluationRequests
    .map((request) => ({
      request,
      scoreResult: scoreByRequestId.get(request.id)
    }))
    .filter((item): item is { request: EvaluationRequestModel; scoreResult: ScoreResult } =>
      typeof item.scoreResult?.totalScore === "number"
    )
    .sort((a, b) => Date.parse(a.request.updatedAt) - Date.parse(b.request.updatedAt));

  const chartData = buildScoreChartData(completedScoreItems, issueCountByRequestId);
  const latestCompletedScoreItem = completedScoreItems[completedScoreItems.length - 1] ?? null;
  const latestRequestId = latestCompletedScoreItem?.request.id ?? null;
  const latestIssues =
    latestRequestId === null
      ? []
      : issueResults.filter((issue) => requestIdByAnalysisResultId.get(issue.analysisResultId) === latestRequestId);
  const summaryItems = buildSummaryItems({
    latestCompletedScoreItem,
    totalEvaluationRequestCount: targetEvaluationRequests.length
  });
  const recentIssueRows: RecentIssueRow[] = latestIssues.map((issue) => {
    const severity = severityChartItems.find((item) => item.key === issue.severity) ?? severityChartItems[0]!;
    return {
      issue,
      severity,
      wcagCriterion: wcagCriterionByIssueCode[issue.issueCode] ?? fallbackWcagCriterion,
      issueGuides: guidesByIssueId.get(issue.id) ?? [],
      analyzerLabel: getAnalyzerTypeLabel(analysisResultById.get(issue.analysisResultId)?.analyzerType)
    };
  });
  const recentIssueDateLabel = latestCompletedScoreItem
    ? formatDateLabel(latestCompletedScoreItem.request.updatedAt)
    : "최근 평가 기준";

  void recentIssueDateLabel;

  return (
    <div className="grid min-h-[calc(100vh-var(--dashboard-top-height)-9rem)] items-stretch gap-3 lg:grid-cols-2">
      <div className="min-h-0">
        <ScoreTrendCard chartData={chartData} summaryItems={summaryItems} />
      </div>
      <RecentIssuesCard rows={recentIssueRows} />
    </div>
  );
}

function buildGuidesByIssueId(improvementGuides: ImprovementGuide[]): Map<number, ImprovementGuide[]> {
  const guidesByIssueId = new Map<number, ImprovementGuide[]>();

  for (const guide of improvementGuides) {
    const currentGuides = guidesByIssueId.get(guide.issueResultId) ?? [];
    currentGuides.push(guide);
    guidesByIssueId.set(guide.issueResultId, currentGuides);
  }

  return guidesByIssueId;
}

function buildScoreChartData(
  completedScoreItems: Array<{ request: EvaluationRequestModel; scoreResult: ScoreResult }>,
  issueCountByRequestId: Map<number, number>
): ScoreChartItem[] {
  const latestScoreByDate = new Map<string, ScoreChartItem>();

  for (const item of completedScoreItems) {
    const date = item.request.updatedAt;
    latestScoreByDate.set(formatDateKey(date), {
      date,
      label: formatShortDate(date),
      score: Math.round(item.scoreResult.totalScore),
      issueCount: issueCountByRequestId.get(item.request.id) ?? 0
    });
  }

  return normalizeChartData([...latestScoreByDate.values()].slice(-18));
}

function buildSummaryItems({
  latestCompletedScoreItem,
  totalEvaluationRequestCount
}: {
  latestCompletedScoreItem: { request: EvaluationRequestModel; scoreResult: ScoreResult } | null;
  totalEvaluationRequestCount: number;
}): SiteSummaryItem[] {
  return [
    {
      label: "최신 점수",
      value: latestCompletedScoreItem ? `${Math.round(latestCompletedScoreItem.scoreResult.totalScore)}` : "-",
      unit: "점"
    },
    {
      label: "등급",
      value: latestCompletedScoreItem ? getScoreGrade(latestCompletedScoreItem.scoreResult.totalScore) : "-",
      unit: latestCompletedScoreItem ? "등급" : ""
    },
    {
      label: "평가 횟수",
      value: `${totalEvaluationRequestCount}`,
      unit: "건"
    }
  ];
}
