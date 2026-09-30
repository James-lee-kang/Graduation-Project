import { getLocatorCategory, type LocatorCategory } from "./locator-labels";
import type { AnalyzerType, IssueResultModel, SeverityLevel } from "@/types/accessibility-domain";

import { formatIssueCodeLabel, normalizeIssueCode, severityChartItems } from "./constants";
import type { LocatorCheckState, LocatorIssueState, RecentIssueRow, SeverityChartItem } from "./types";

export const analyzerLabels: Record<AnalyzerType, string> = {
  RULE_BASED: "규칙",
  AI_TEXT: "텍스트",
  CV_VISION: "시각"
};

const analyzerOrder: AnalyzerType[] = ["RULE_BASED", "AI_TEXT", "CV_VISION"];
const severityRank: Record<SeverityLevel, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
// One critical issue outweighs several minor ones when ordering fix units.
const severityWeight: Record<SeverityLevel, number> = { CRITICAL: 8, HIGH: 4, MEDIUM: 2, LOW: 1 };

function compareRows(left: RecentIssueRow, right: RecentIssueRow): number {
  return severityRank[left.severity.key] - severityRank[right.severity.key] || left.issue.id - right.issue.id;
}

function severityItem(key: SeverityLevel): SeverityChartItem {
  return severityChartItems.find((item) => item.key === key) ?? severityChartItems[0]!;
}

function highestSeverity(rows: readonly RecentIssueRow[]): SeverityChartItem {
  let best: SeverityLevel = "LOW";
  for (const row of rows) {
    if (severityRank[row.severity.key] < severityRank[best]) best = row.severity.key;
  }
  return severityItem(best);
}

function mostFrequent(values: readonly string[]): string {
  const counts = new Map<string, number>();
  let best = "";
  let bestCount = 0;
  for (const value of values) {
    const count = (counts.get(value) ?? 0) + 1;
    counts.set(value, count);
    if (count > bestCount) {
      best = value;
      bestCount = count;
    }
  }
  return best;
}

// Whether the current live page can point at the issue. "other-state" issues
// are on the page but need the viewer to restore a slide first.
export type ReportLocationStatus = "checking" | "disconnected" | LocatorCategory;

export function getReportLocationStatus(
  state: LocatorIssueState | undefined,
  checkState: LocatorCheckState
): ReportLocationStatus {
  if (checkState === "error") return "disconnected";
  if (!state) return "checking";
  return getLocatorCategory(state);
}

export function canShowOnPage(status: ReportLocationStatus): boolean {
  return status === "on-page" || status === "other-state";
}

export type ReportSummary = {
  total: number;
  severities: Array<SeverityChartItem & { count: number }>;
  analyzers: Array<{ analyzer: AnalyzerType; label: string; count: number }>;
};

export function summarizeReport(rows: readonly RecentIssueRow[]): ReportSummary {
  const severityCounts = new Map<SeverityLevel, number>();
  const analyzerCounts = new Map<AnalyzerType, number>();
  for (const row of rows) {
    severityCounts.set(row.severity.key, (severityCounts.get(row.severity.key) ?? 0) + 1);
    if (row.analyzerType) analyzerCounts.set(row.analyzerType, (analyzerCounts.get(row.analyzerType) ?? 0) + 1);
  }
  return {
    total: rows.length,
    severities: severityChartItems.map((item) => ({ ...item, count: severityCounts.get(item.key) ?? 0 })),
    analyzers: analyzerOrder.map((analyzer) => ({
      analyzer,
      label: analyzerLabels[analyzer],
      count: analyzerCounts.get(analyzer) ?? 0
    }))
  };
}

export type ReportLocationSummary = Record<ReportLocationStatus, number>;

export function summarizeReportLocations(
  rows: readonly RecentIssueRow[],
  locationOf: (row: RecentIssueRow) => ReportLocationStatus
): ReportLocationSummary {
  const summary: ReportLocationSummary = {
    checking: 0, disconnected: 0, "on-page": 0, "other-state": 0, "page-setting": 0, outdated: 0, unavailable: 0
  };
  for (const row of rows) summary[locationOf(row)] += 1;
  return summary;
}

export type ReportFixUnit = {
  key: string;
  title: string;
  code: string;
  codeLabel: string;
  severity: SeverityChartItem;
  count: number;
  analyzers: AnalyzerType[];
};

// A fix unit groups issues a developer resolves with the same change: one
// engine rule, or one criterion/title pair when the engine has no rule id.
function fixUnitKey(row: RecentIssueRow): string {
  const code = normalizeIssueCode(row.issue.issueCode);
  return row.issue.ruleId
    ? `rule:${row.issue.ruleId}:${code}`
    : `${row.analyzerType ?? "UNKNOWN"}:${code}:${row.issue.issueTitle}`;
}

export function buildFixPriorities(rows: readonly RecentIssueRow[], limit = 5): ReportFixUnit[] {
  const units = new Map<string, RecentIssueRow[]>();
  for (const row of rows) {
    const key = fixUnitKey(row);
    const group = units.get(key);
    if (group) group.push(row);
    else units.set(key, [row]);
  }
  return [...units.entries()]
    .map(([key, group]) => {
      const code = normalizeIssueCode(group[0]!.issue.issueCode);
      return {
        unit: {
          key,
          title: mostFrequent(group.map((row) => row.issue.issueTitle)),
          code,
          codeLabel: formatIssueCodeLabel(code),
          severity: highestSeverity(group),
          count: group.length,
          analyzers: analyzerOrder.filter((analyzer) => group.some((row) => row.analyzerType === analyzer))
        },
        weight: group.reduce((total, row) => total + severityWeight[row.severity.key], 0)
      };
    })
    .sort((left, right) =>
      right.weight - left.weight ||
      severityRank[left.unit.severity.key] - severityRank[right.unit.severity.key] ||
      right.unit.count - left.unit.count ||
      left.unit.title.localeCompare(right.unit.title, "ko")
    )
    .slice(0, Math.max(0, limit))
    .map(({ unit }) => unit);
}

export type ReportCriterionGroup = {
  code: string;
  codeLabel: string;
  title: string;
  severity: SeverityChartItem;
  rows: RecentIssueRow[];
};

// KWCAG numbers sort numerically; WCAG-only and unknown codes follow them.
function criterionSortKey(code: string): [number, number[], string] {
  const kwcag = /^[0-9]+(?:\.[0-9]+)*$/.exec(code);
  if (kwcag) return [0, code.split(".").map(Number), code];
  const wcag = /^WCAG\s+([0-9]+(?:\.[0-9]+)*)$/i.exec(code);
  if (wcag) return [1, wcag[1]!.split(".").map(Number), code];
  return [2, [], code];
}

function compareCriteria(left: string, right: string): number {
  const [leftTier, leftParts, leftCode] = criterionSortKey(left);
  const [rightTier, rightParts, rightCode] = criterionSortKey(right);
  if (leftTier !== rightTier) return leftTier - rightTier;
  for (let index = 0; index < Math.max(leftParts.length, rightParts.length); index += 1) {
    const difference = (leftParts[index] ?? -1) - (rightParts[index] ?? -1);
    if (difference !== 0) return difference;
  }
  return leftCode.localeCompare(rightCode);
}

export function groupByCriterion(rows: readonly RecentIssueRow[]): ReportCriterionGroup[] {
  const groups = new Map<string, RecentIssueRow[]>();
  for (const row of rows) {
    const code = normalizeIssueCode(row.issue.issueCode) || "기타";
    const group = groups.get(code);
    if (group) group.push(row);
    else groups.set(code, [row]);
  }
  return [...groups.entries()]
    .sort(([left], [right]) => compareCriteria(left, right))
    .map(([code, group]) => ({
      code,
      codeLabel: formatIssueCodeLabel(code),
      title: mostFrequent(group.map((row) => row.issue.issueTitle)),
      severity: highestSeverity(group),
      rows: [...group].sort(compareRows)
    }));
}

export type ReportFilters = {
  severity: SeverityLevel | "ALL";
  analyzer: AnalyzerType | "ALL";
  location: "ALL" | "on-page" | "outdated" | "page-setting" | "unavailable";
  query: string;
};

export const defaultReportFilters: ReportFilters = { severity: "ALL", analyzer: "ALL", location: "ALL", query: "" };

export function filterReportRows(
  rows: readonly RecentIssueRow[],
  filters: ReportFilters,
  locationOf: (row: RecentIssueRow) => ReportLocationStatus
): RecentIssueRow[] {
  const query = filters.query.trim().toLocaleLowerCase("ko");
  return rows.filter((row) => {
    if (filters.severity !== "ALL" && row.severity.key !== filters.severity) return false;
    if (filters.analyzer !== "ALL" && row.analyzerType !== filters.analyzer) return false;
    if (filters.location !== "ALL") {
      const status = locationOf(row);
      if (filters.location === "on-page" ? !canShowOnPage(status) : status !== filters.location) return false;
    }
    if (!query) return true;
    const { issue } = row;
    return [
      issue.issueTitle,
      formatIssueCodeLabel(issue.issueCode),
      issue.locationPath,
      issue.locator?.htmlSnippet ?? "",
      issue.message
    ].some((value) => value.toLocaleLowerCase("ko").includes(query));
  });
}

// Section labels written by the rule guide, the text analysis formatter and
// the backend's recommendation suffix; the report shows them as sub-headings.
const descriptionHeadings = new Set(["개선 안내", "분석 문장", "개선 필요", "개선 제안", "수정 예시", "수정 이유"]);
const inlineHeadingPattern = /^(권장사항)\s*:\s*/;

export type ReportDescriptionSection = { heading: string | null; body: string };

export function splitDescriptionSections(description: string): ReportDescriptionSection[] {
  return description
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter((block) => block.length > 0)
    .map((block) => {
      const inline = inlineHeadingPattern.exec(block);
      if (inline) return { heading: inline[1]!, body: block.slice(inline[0].length).trim() };
      const newline = block.indexOf("\n");
      const firstLine = newline === -1 ? "" : block.slice(0, newline).trim();
      return descriptionHeadings.has(firstLine)
        ? { heading: firstLine, body: block.slice(newline + 1).trim() }
        : { heading: null, body: block };
    });
}

export type ReportIssueLocation =
  | { kind: "path"; steps: Array<{ context: string; selector: string }> }
  | { kind: "coordinates"; x: number; y: number; width: number | null; height: number | null }
  | { kind: "text"; value: string }
  | null;

// Coordinate-only findings (the visual engine) keep a coordinate label in
// `selector`; it must not be presented as a CSS selector a developer can search.
export function describeIssueLocation(issue: IssueResultModel): ReportIssueLocation {
  const locator = issue.locator;
  const steps = (Array.isArray(locator?.pathSteps) ? locator.pathSteps : [])
    .filter((step) => typeof step?.selector === "string" && step.selector.trim().length > 0)
    .map((step) => ({ context: String(step.context), selector: step.selector.trim() }));
  if (steps.length > 0) return { kind: "path", steps };
  if (typeof locator?.x === "number" && typeof locator.y === "number") {
    return {
      kind: "coordinates",
      x: locator.x,
      y: locator.y,
      width: typeof locator.width === "number" ? locator.width : null,
      height: typeof locator.height === "number" ? locator.height : null
    };
  }
  const text = issue.locationPath.trim();
  return text ? { kind: "text", value: text } : null;
}
