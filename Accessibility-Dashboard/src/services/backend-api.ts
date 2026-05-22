import { buildApiUrl } from "@/config/api";
import type {
  AnalysisResult,
  DashboardViewModel,
  CreateEvaluationTargetInput,
  EvaluationIssue,
  EvaluationRequestModel,
  EvaluationTarget,
  EvaluationTargetModel,
  EvaluationResultSummary,
  ImprovementGuide,
  IssueResultModel,
  Organization,
  OrganizationModel,
  ScoreResult
} from "@/types/accessibility-domain";

type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  message?: string | null;
  error?: string | null;
};

type ApiRequestMethod = "GET" | "POST" | "PATCH" | "DELETE";

type ApiRequestOptions = {
  method?: ApiRequestMethod;
  body?: unknown;
  signal?: AbortSignal;
  optionalStatuses?: number[];
};

type ApiRequestErrorInput = {
  method: ApiRequestMethod;
  path: string;
  payload: unknown;
  status: number | null;
  url: string;
  message: string;
};

export class ApiRequestError extends Error {
  readonly method: ApiRequestMethod;
  readonly path: string;
  readonly payload: unknown;
  readonly status: number | null;
  readonly url: string;

  constructor({ method, path, payload, status, url, message }: ApiRequestErrorInput) {
    const statusLabel = status === null ? "" : `, HTTP ${status}`;
    super(`${message} [${method} ${path}${statusLabel}]`);
    this.name = "ApiRequestError";
    this.method = method;
    this.path = path;
    this.payload = payload;
    this.status = status;
    this.url = url;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }

  return fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function isApiEnvelope<T = unknown>(value: unknown): value is ApiEnvelope<T> {
  return (
    isRecord(value) &&
    typeof value.success === "boolean" &&
    (!("message" in value) || value.message === null || typeof value.message === "string") &&
    (!("error" in value) || value.error === null || typeof value.error === "string")
  );
}

function getErrorMessage(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) {
    return fallback;
  }

  if (typeof payload.message === "string" && payload.message.trim().length > 0) {
    return payload.message;
  }

  if (typeof payload.error === "string" && payload.error.trim().length > 0) {
    return payload.error;
  }

  return fallback;
}

async function readJsonResponse(
  response: Response,
  context: { method: ApiRequestMethod; path: string; url: string }
): Promise<unknown> {
  const text = await response.text();
  if (text.trim().length === 0) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new ApiRequestError({
      method: context.method,
      path: context.path,
      payload: text.slice(0, 500),
      status: response.status,
      url: context.url,
      message: "Invalid JSON response."
    });
  }
}

async function apiRequest<T = unknown>(
  path: string,
  { method = "GET", body, signal, optionalStatuses = [] }: ApiRequestOptions = {}
): Promise<T> {
  const headers: HeadersInit = {
    Accept: "application/json"
  };
  const requestInit: RequestInit = {
    method,
    headers,
    signal
  };

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    requestInit.body = JSON.stringify(body);
  }

  const url = buildApiUrl(path);
  let response: Response;

  try {
    response = await fetch(url, {
      ...requestInit
    });
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }

    throw new ApiRequestError({
      method,
      path,
      payload: error,
      status: null,
      url,
      message: "Network request failed."
    });
  }

  const payload = await readJsonResponse(response, { method, path, url });

  if (!response.ok) {
    if (optionalStatuses.includes(response.status)) {
      return null as T;
    }

    throw new ApiRequestError({
      method,
      path,
      payload,
      status: response.status,
      url,
      message: getErrorMessage(payload, response.statusText || "API request failed.")
    });
  }

  if (isApiEnvelope<T>(payload)) {
    if (!payload.success) {
      throw new ApiRequestError({
        method,
        path,
        payload,
        status: response.status,
        url,
        message: getErrorMessage(payload, "API request failed.")
      });
    }

    return ("data" in payload ? payload.data : null) as T;
  }

  return payload as T;
}

async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(path, { signal });
}

function compareByUpdatedAt(left: EvaluationRequestModel, right: EvaluationRequestModel): number {
  return Date.parse(left.updatedAt) - Date.parse(right.updatedAt);
}

function fetchOrganizations(signal?: AbortSignal): Promise<Organization[]> {
  return apiGet<Organization[]>("/organizations", signal);
}

function fetchEvaluationTargets(organizationId: number, signal?: AbortSignal): Promise<EvaluationTarget[]> {
  return apiGet<EvaluationTarget[]>(`/organizations/${organizationId}/evaluation-targets`, signal);
}

function buildLatestRequestByTargetId(requests: EvaluationRequestModel[]): Map<number, EvaluationRequestModel> {
  const requestsByTargetId = new Map<number, EvaluationRequestModel[]>();
  for (const request of requests) {
    const current = requestsByTargetId.get(request.evaluationTargetId) ?? [];
    current.push(request);
    requestsByTargetId.set(request.evaluationTargetId, current);
  }

  return new Map(
    [...requestsByTargetId.entries()].map(([targetId, targetRequests]) => {
      const sortedRequests = [...targetRequests].sort(compareByUpdatedAt);
      return [targetId, sortedRequests[sortedRequests.length - 1]!];
    })
  );
}

function buildOrganizationsFromApi(
  organizations: Organization[],
  evaluationTargets: EvaluationTarget[],
  requests: EvaluationRequestModel[]
): OrganizationModel[] {
  const targetsByOrganizationId = new Map<number, EvaluationTarget[]>();
  const latestRequestByTargetId = buildLatestRequestByTargetId(requests);

  for (const target of evaluationTargets) {
    const currentTargets = targetsByOrganizationId.get(target.organizationId) ?? [];
    currentTargets.push(target);
    targetsByOrganizationId.set(target.organizationId, currentTargets);
  }

  return organizations
    .map((organization): OrganizationModel => {
      const targets = targetsByOrganizationId.get(organization.id) ?? [];
      const evaluationTargetModels = targets.map((target): EvaluationTargetModel => {
        const latestRequest = latestRequestByTargetId.get(target.id);

        return {
          id: target.id,
          name: target.name,
          targetType: target.targetType,
          accessUrl: target.accessUrl,
          status: latestRequest?.status ?? target.status,
          createdAt: target.createdAt
        };
      });
      const latestRequest = evaluationTargetModels
        .map((target) => latestRequestByTargetId.get(target.id))
        .filter((request): request is EvaluationRequestModel => request !== undefined)
        .sort(compareByUpdatedAt);
      const latestOrganizationRequest = latestRequest[latestRequest.length - 1];

      return {
        id: organization.id,
        name: organization.name,
        type: organization.type,
        homepageUrl: organization.homepageUrl ?? "",
        description: organization.description ?? "",
        status: latestOrganizationRequest?.status ?? organization.status,
        createdAt: organization.createdAt,
        updatedAt: latestOrganizationRequest?.updatedAt ?? organization.updatedAt,
        evaluationTargets: evaluationTargetModels
      };
    })
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
}

function fetchEvaluationResultSummary(requestId: number, signal?: AbortSignal): Promise<EvaluationResultSummary> {
  return apiGet<EvaluationResultSummary>(`/results/requests/${requestId}/summary`, signal);
}

function fetchEvaluationIssues(requestId: number, signal?: AbortSignal): Promise<EvaluationIssue[]> {
  return apiGet<EvaluationIssue[]>(`/results/requests/${requestId}/issues`, signal);
}

function fetchScoreResult(requestId: number, signal?: AbortSignal): Promise<ScoreResult> {
  return apiGet<ScoreResult>(`/scores/requests/${requestId}`, signal);
}

async function fetchEvaluationIssuesSafely(requestId: number, signal?: AbortSignal): Promise<EvaluationIssue[]> {
  try {
    return await fetchEvaluationIssues(requestId, signal);
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }

    console.warn(`Failed to load evaluation issues for request ${requestId}.`, error);
    return [];
  }
}

async function fetchScoreResultSafely(
  summary: EvaluationResultSummary,
  requestById: Map<number, EvaluationRequestModel>,
  signal?: AbortSignal
): Promise<ScoreResult | null> {
  try {
    return await fetchScoreResult(summary.requestId, signal);
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }

    console.warn(`Failed to load score result for request ${summary.requestId}.`, error);
    return summaryToScoreResult(summary, requestById);
  }
}

function summaryToScoreResult(
  summary: EvaluationResultSummary,
  requestById: Map<number, EvaluationRequestModel>
): ScoreResult | null {
  if (typeof summary.totalScore !== "number") {
    return null;
  }

  const request = requestById.get(summary.requestId);
  const timestamp = request?.updatedAt ?? summary.requestedAt ?? "";

  return {
    id: summary.requestId,
    evaluationRequestId: summary.requestId,
    totalScore: summary.totalScore,
    ruleScore: 0,
    aiScore: 0,
    cvScore: 0,
    createdAt: request?.createdAt ?? timestamp,
    updatedAt: timestamp
  };
}

function getSyntheticAnalysisId(requestId: number, module: string): number {
  const moduleIndexMap: Record<string, number> = {
    rule_based: 1,
    text_difficulty: 2,
    text_suggestions: 3,
    cv_visual: 4
  };

  return -(requestId * 10 + (moduleIndexMap[module] ?? 9));
}

function moduleToAnalyzerType(module: string): AnalysisResult["analyzerType"] {
  const normalizedModule = module.toLowerCase();
  if (normalizedModule.includes("rule")) {
    return "RULE_BASED";
  }
  if (normalizedModule.includes("cv") || normalizedModule.includes("visual")) {
    return "CV_VISION";
  }
  return "AI_TEXT";
}

function issueSeverityToUiSeverity(severity: EvaluationIssue["severity"]): IssueResultModel["severity"] {
  if (severity === "CRITICAL") {
    return "CRITICAL";
  }
  if (severity === "SERIOUS") {
    return "HIGH";
  }
  if (severity === "MODERATE") {
    return "MEDIUM";
  }
  return "LOW";
}

function issueIdToNumber(issue: EvaluationIssue, index: number): number {
  if (typeof issue.id === "number") {
    return issue.id;
  }

  const parsed = Number.parseInt(issue.id, 10);
  return Number.isFinite(parsed) ? parsed : issue.requestId * 10000 + index + 1;
}

function buildIssueViewModels(
  evaluationIssues: EvaluationIssue[],
  requestById: Map<number, EvaluationRequestModel>
): { analysisResults: AnalysisResult[]; issueResults: IssueResultModel[] } {
  const analysisResultById = new Map<number, AnalysisResult>();
  const issueResults = evaluationIssues.map((issue, index): IssueResultModel => {
    const request = requestById.get(issue.requestId);
    const timestamp = issue.createdAt ?? request?.updatedAt ?? "";
    const analysisResultId = getSyntheticAnalysisId(issue.requestId, issue.module);

    if (!analysisResultById.has(analysisResultId)) {
      analysisResultById.set(analysisResultId, {
        id: analysisResultId,
        evaluationRequestId: issue.requestId,
        analyzerType: moduleToAnalyzerType(issue.module),
        status: "SUCCESS",
        summary: "",
        startedAt: null,
        completedAt: timestamp || null,
        createdAt: timestamp,
        updatedAt: timestamp
      });
    }

    const description = issue.description.trim();
    const recommendation = issue.recommendation?.trim() ?? "";
    const message =
      recommendation.length > 0 && !description.includes(recommendation)
        ? `${description}\n\n권장사항: ${recommendation}`
        : description;

    return {
      id: issueIdToNumber(issue, index),
      analysisResultId,
      issueCode: issue.wcagCode ?? issue.module,
      issueTitle: issue.title,
      severity: issueSeverityToUiSeverity(issue.severity),
      locationPath: issue.selector ?? "",
      message,
      recommendation: issue.recommendation ?? null,
      resolved: false,
      createdAt: timestamp,
      updatedAt: timestamp
    };
  });

  return {
    analysisResults: [...analysisResultById.values()],
    issueResults
  };
}

export async function createOrganizationModel(input: { name: string; description: string }): Promise<void> {
  await apiRequest("/organizations", {
    method: "POST",
    body: input
  });
}

export async function updateOrganizationModel({
  projectId,
  name,
  description
}: {
  projectId: number;
  name: string;
  description: string;
}): Promise<void> {
  await apiRequest(`/organizations/${projectId}`, {
    method: "PATCH",
    body: {
      name,
      description
    }
  });
}

export async function deleteOrganizationModel(projectId: number): Promise<void> {
  await apiRequest(`/organizations/${projectId}`, {
    method: "DELETE"
  });
}

export async function createEvaluationTargetModel({
  projectId,
  name,
  accessUrl
}: CreateEvaluationTargetInput): Promise<void> {
  await apiRequest(`/organizations/${projectId}/evaluation-targets`, {
    method: "POST",
    body: {
      name,
      accessUrl
    }
  });
}

export async function updateEvaluationTargetModel({
  projectId,
  siteId,
  name,
  accessUrl
}: {
  projectId: number;
  siteId: number;
  name: string;
  accessUrl: string;
}): Promise<void> {
  await apiRequest(`/organizations/${projectId}/evaluation-targets/${siteId}`, {
    method: "PATCH",
    body: {
      name,
      accessUrl
    }
  });
}

export async function deleteEvaluationTargetModel({
  projectId,
  siteId
}: {
  projectId: number;
  siteId: number;
}): Promise<void> {
  await apiRequest(`/organizations/${projectId}/evaluation-targets/${siteId}`, {
    method: "DELETE"
  });
}

export async function requestEvaluationTargetRescan(targetId: number): Promise<number | null> {
  void targetId;
  throw new ApiRequestError({
    method: "POST",
    path: "/requests",
    payload: null,
    status: null,
    url: buildApiUrl("/requests"),
    message: "아직 지원되지 않는 기능입니다."
  });
}

export async function fetchDashboardViewModel(signal?: AbortSignal): Promise<DashboardViewModel> {
  const [requests, organizations] = await Promise.all([apiGet<EvaluationRequestModel[]>("/requests", signal), fetchOrganizations(signal)]);
  const evaluationTargets = (
    await Promise.all(organizations.map((organization) => fetchEvaluationTargets(organization.id, signal)))
  ).flat();
  const requestById = new Map(requests.map((request) => [request.id, request]));
  const completedRequests = requests.filter((request) => request.status === "COMPLETED");
  const [resultSummaries, evaluationIssuesByRequest] = await Promise.all([
    Promise.all(completedRequests.map((request) => fetchEvaluationResultSummary(request.id, signal))),
    Promise.all(completedRequests.map((request) => fetchEvaluationIssuesSafely(request.id, signal)))
  ]);
  const scoreResults = (
    await Promise.all(resultSummaries.map((summary) => fetchScoreResultSafely(summary, requestById, signal)))
  ).filter((scoreResult): scoreResult is ScoreResult => scoreResult !== null);
  const evaluationIssues = evaluationIssuesByRequest.flat();
  const issueViewModels = buildIssueViewModels(evaluationIssues, requestById);
  const improvementGuides: ImprovementGuide[] = [];

  return {
    organizations: buildOrganizationsFromApi(organizations, evaluationTargets, requests),
    evaluationRequests: requests,
    resultSummaries,
    evaluationIssues,
    analysisResults: issueViewModels.analysisResults,
    scoreResults,
    scoreDetails: [],
    issueResults: issueViewModels.issueResults,
    improvementGuides
  };
}
