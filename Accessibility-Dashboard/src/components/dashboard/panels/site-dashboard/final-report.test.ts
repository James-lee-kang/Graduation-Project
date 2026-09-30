import { describe, expect, it } from "vitest";

import type { AnalyzerType, IssueLocator, SeverityLevel } from "@/types/accessibility-domain";

import { severityChartItems } from "./constants";
import { parseDashboardView } from "./dashboard-view-tabs";
import {
  buildFixPriorities,
  defaultReportFilters,
  describeIssueLocation,
  filterReportRows,
  getReportLocationStatus,
  groupByCriterion,
  splitDescriptionSections,
  summarizeReport,
  summarizeReportLocations,
  type ReportLocationStatus
} from "./final-report";
import type { RecentIssueRow } from "./types";

function row(id: number, options: {
  severity?: SeverityLevel;
  analyzer?: AnalyzerType;
  code?: string;
  title?: string;
  ruleId?: string | null;
  path?: string;
  locator?: IssueLocator | null;
  message?: string;
} = {}): RecentIssueRow {
  const severity = severityChartItems.find((item) => item.key === (options.severity ?? "HIGH"))!;
  return {
    severity,
    analyzerType: options.analyzer ?? "RULE_BASED",
    issue: {
      id,
      analysisResultId: 1,
      issueCode: options.code ?? "5.1.1",
      issueTitle: options.title ?? "적절한 대체 텍스트 제공",
      ruleId: options.ruleId === undefined ? "image-alt" : options.ruleId,
      severity: severity.key,
      locationPath: options.path ?? "#image",
      locator: options.locator === undefined
        ? { pathSteps: [{ context: "DOCUMENT", selector: "#image" }], htmlSnippet: "<img src=\"a.png\">" }
        : options.locator,
      message: options.message ?? "이미지 설명",
      recommendation: null,
      resolved: false,
      createdAt: "2026-09-28T00:00:00Z",
      updatedAt: "2026-09-28T00:00:00Z"
    }
  };
}

describe("dashboard view", () => {
  it("accepts only the report view and falls back to results", () => {
    expect(parseDashboardView("report")).toBe("report");
    expect(parseDashboardView(null)).toBe("results");
    expect(parseDashboardView("REPORT")).toBe("results");
    expect(parseDashboardView("")).toBe("results");
  });
});

describe("report location status", () => {
  it("separates live positions, restorable states and unavailable findings", () => {
    expect(getReportLocationStatus({ status: "VISIBLE" }, "ready")).toBe("on-page");
    expect(getReportLocationStatus({ status: "OFFSCREEN" }, "ready")).toBe("on-page");
    expect(getReportLocationStatus({ status: "HIDDEN_STATE", recoverable: true }, "ready")).toBe("other-state");
    expect(getReportLocationStatus({ status: "HIDDEN_STATE", recoverable: false, reason: "DISPLAY_NONE" }, "ready")).toBe("unavailable");
    expect(getReportLocationStatus({ status: "UNAVAILABLE", reason: "FRAME_UNSUPPORTED" }, "ready")).toBe("unavailable");
    expect(getReportLocationStatus({ status: "VISIBLE", reason: "SCREEN_READER_ONLY", ownerKind: "BUTTON" }, "ready"))
      .toBe("on-page");
    expect(getReportLocationStatus({ status: "UNAVAILABLE", reason: "DOCUMENT_METADATA" }, "ready")).toBe("page-setting");
    expect(getReportLocationStatus({ status: "UNAVAILABLE", reason: "ELEMENT_CONTENT_CHANGED" }, "ready")).toBe("outdated");
    expect(getReportLocationStatus({ status: "UNAVAILABLE", reason: "SELECTOR_NOT_FOUND" }, "ready")).toBe("outdated");
  });

  it("does not claim a position before the viewer reports one or after it disconnects", () => {
    expect(getReportLocationStatus(undefined, "loading")).toBe("checking");
    expect(getReportLocationStatus(undefined, "ready")).toBe("checking");
    expect(getReportLocationStatus({ status: "VISIBLE" }, "error")).toBe("disconnected");
  });
});

describe("report summary", () => {
  it("counts every severity and engine, including zero counts", () => {
    const summary = summarizeReport([
      row(1, { severity: "CRITICAL" }),
      row(2, { severity: "HIGH", analyzer: "CV_VISION" }),
      row(3, { severity: "HIGH", analyzer: "CV_VISION" })
    ]);
    expect(summary.total).toBe(3);
    expect(summary.severities.map(({ key, count }) => [key, count])).toEqual([
      ["CRITICAL", 1], ["HIGH", 2], ["MEDIUM", 0], ["LOW", 0]
    ]);
    expect(summary.analyzers.map(({ label, count }) => [label, count])).toEqual([
      ["규칙", 1], ["텍스트", 0], ["시각", 2]
    ]);
  });

  it("counts location outcomes", () => {
    const statuses: Record<number, ReportLocationStatus> = {
      1: "on-page", 2: "unavailable", 3: "unavailable", 4: "outdated", 5: "page-setting"
    };
    expect(summarizeReportLocations([1, 2, 3, 4, 5].map((id) => row(id)), (item) => statuses[item.issue.id]!)).toEqual({
      checking: 0, disconnected: 0, "on-page": 1, "other-state": 0, "page-setting": 1, outdated: 1, unavailable: 2
    });
  });
});

describe("fix priorities", () => {
  it("ranks fix units by weighted severity and keeps one entry per rule", () => {
    const priorities = buildFixPriorities([
      ...Array.from({ length: 3 }, (_, index) => row(10 + index, { severity: "LOW", ruleId: "color-contrast", code: "5.4.3", title: "명도 대비" })),
      row(20, { severity: "CRITICAL" }),
      row(21, { severity: "HIGH" }),
      row(30, { severity: "MEDIUM", analyzer: "AI_TEXT", ruleId: null, code: "6.4.3", title: "적절한 링크 텍스트" })
    ]);
    expect(priorities.map(({ title, count, severity }) => [title, count, severity.key])).toEqual([
      ["적절한 대체 텍스트 제공", 2, "CRITICAL"],
      ["명도 대비", 3, "LOW"],
      ["적절한 링크 텍스트", 1, "MEDIUM"]
    ]);
    expect(priorities[0]!.codeLabel).toBe("KWCAG 5.1.1");
  });

  it("does not merge engine findings without a rule id across titles or engines", () => {
    const priorities = buildFixPriorities([
      row(1, { analyzer: "AI_TEXT", ruleId: null, code: "6.4.3", title: "링크 A" }),
      row(2, { analyzer: "AI_TEXT", ruleId: null, code: "6.4.3", title: "링크 B" }),
      row(3, { analyzer: "CV_VISION", ruleId: null, code: "6.4.3", title: "링크 A" })
    ], 10);
    expect(priorities).toHaveLength(3);
    expect(buildFixPriorities([row(1)], 0)).toEqual([]);
  });
});

describe("criterion groups", () => {
  it("orders KWCAG numerically before WCAG-only codes and sorts issues by severity", () => {
    const groups = groupByCriterion([
      row(1, { code: "WCAG 3.1.5", title: "읽기 수준", severity: "MEDIUM" }),
      row(2, { code: "5.10.1", title: "후순위" }),
      row(3, { code: "5.4.3", title: "명도 대비", severity: "LOW" }),
      row(4, { code: "5.4.3", title: "명도 대비", severity: "CRITICAL" }),
      row(5, { code: "img-alt", title: "대체 텍스트" })
    ]);
    expect(groups.map(({ codeLabel }) => codeLabel)).toEqual([
      "KWCAG 5.1.1", "KWCAG 5.4.3", "KWCAG 5.10.1", "WCAG 3.1.5"
    ]);
    const contrast = groups[1]!;
    expect(contrast.rows.map(({ issue }) => issue.id)).toEqual([4, 3]);
    expect(contrast.severity.key).toBe("CRITICAL");
  });
});

describe("report filters", () => {
  const rows = [
    row(1, { severity: "CRITICAL", path: "#hero-banner" }),
    row(2, { severity: "LOW", analyzer: "CV_VISION", locator: null, path: "x=1, y=2", message: "text=다운로드" }),
    row(3, { severity: "LOW", code: "5.4.3", title: "명도 대비" })
  ];
  const location = (item: RecentIssueRow): ReportLocationStatus =>
    item.issue.id === 1 ? "on-page" : item.issue.id === 2 ? "unavailable" : "other-state";

  it("combines severity, engine, location and text queries", () => {
    const ids = (filters: Partial<typeof defaultReportFilters>) =>
      filterReportRows(rows, { ...defaultReportFilters, ...filters }, location).map(({ issue }) => issue.id);
    expect(ids({})).toEqual([1, 2, 3]);
    expect(ids({ severity: "LOW" })).toEqual([2, 3]);
    expect(ids({ analyzer: "CV_VISION" })).toEqual([2]);
    expect(ids({ location: "on-page" })).toEqual([1, 3]);
    expect(ids({ location: "unavailable" })).toEqual([2]);
    expect(ids({ query: "  HERO " })).toEqual([1]);
    expect(ids({ query: "kwcag 5.4.3" })).toEqual([3]);
    expect(ids({ query: "다운로드", severity: "CRITICAL" })).toEqual([]);
  });
});

describe("issue location description", () => {
  it("prefers stored path steps", () => {
    expect(describeIssueLocation(row(1, {
      locator: { pathSteps: [{ context: "DOCUMENT", selector: "#ad" }, { context: "FRAME", selector: " .banner " }] }
    }).issue)).toEqual({ kind: "path", steps: [{ context: "DOCUMENT", selector: "#ad" }, { context: "FRAME", selector: ".banner" }] });
  });

  it("presents coordinate-only findings as coordinates instead of a selector", () => {
    expect(describeIssueLocation(row(1, {
      path: "x=803, y=13, width=39, height=12",
      locator: { pathSteps: [], x: 803, y: 13, width: 39, height: 12, coordinateSpace: "SCREENSHOT_PX" }
    }).issue)).toEqual({ kind: "coordinates", x: 803, y: 13, width: 39, height: 12 });
  });

  it("falls back to the stored text and reports missing locations", () => {
    expect(describeIssueLocation(row(1, { locator: null, path: " main > a " }).issue)).toEqual({ kind: "text", value: "main > a" });
    expect(describeIssueLocation(row(1, { locator: null, path: "" }).issue)).toBeNull();
  });
});

describe("issue description sections", () => {
  it("turns known section labels into headings and keeps the lead paragraph", () => {
    expect(splitDescriptionSections("대체 텍스트가 없습니다.\n\n개선 안내\nalt를 제공하세요.")).toEqual([
      { heading: null, body: "대체 텍스트가 없습니다." },
      { heading: "개선 안내", body: "alt를 제공하세요." }
    ]);
    expect(splitDescriptionSections("문장이 어렵습니다.\n\n권장사항: 쉬운 단어로 바꾸세요.")).toEqual([
      { heading: null, body: "문장이 어렵습니다." },
      { heading: "권장사항", body: "쉬운 단어로 바꾸세요." }
    ]);
  });

  it("leaves unknown first lines and single-line text as body text", () => {
    expect(splitDescriptionSections("text=다운로드, contrast=2.10:1")).toEqual([
      { heading: null, body: "text=다운로드, contrast=2.10:1" }
    ]);
    expect(splitDescriptionSections("첫 줄\n둘째 줄\n\n\n개선 안내")).toEqual([
      { heading: null, body: "첫 줄\n둘째 줄" },
      { heading: null, body: "개선 안내" }
    ]);
  });
});
