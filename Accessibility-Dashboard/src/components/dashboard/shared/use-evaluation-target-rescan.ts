import { useCallback, useState } from "react";

import { getApiErrorMessage, requestEvaluationTargetRescan } from "@/services/backend-api";
import type { DashboardViewModel, EvaluationTargetModel, OrganizationModel } from "@/types/accessibility-domain";

import type { LoadDashboard } from "./use-dashboard-data";

const RESCAN_RESULT_POLL_ATTEMPTS = 12;
const RESCAN_RESULT_POLL_INTERVAL_MS = 2000;

function wait(milliseconds: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });
}

function getLatestRequestForTarget(data: DashboardViewModel | null, targetId: number) {
  return [...(data?.evaluationRequests ?? [])]
    .filter((request) => request.evaluationTargetId === targetId)
    .sort((left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt))[0] ?? null;
}

function isFinalRequestStatus(status: string) {
  return status === "COMPLETED" || status === "FAILED";
}

export function useEvaluationTargetRescan({
  dashboardData,
  loadDashboard,
  onError,
  selectedEvaluationTargetModel,
  selectedOrganizationModel
}: {
  dashboardData: DashboardViewModel | null;
  loadDashboard: LoadDashboard;
  onError: (message: string) => void;
  selectedEvaluationTargetModel: EvaluationTargetModel | null;
  selectedOrganizationModel: OrganizationModel | null;
}) {
  const [isRescanningSite, setIsRescanningSite] = useState(false);

  const handleRescanEvaluationTargetModel = useCallback(async () => {
    if (!selectedOrganizationModel || !selectedEvaluationTargetModel || isRescanningSite) {
      return;
    }

    const targetId = selectedEvaluationTargetModel.id;
    const previousLatestRequest = getLatestRequestForTarget(dashboardData, targetId);
    setIsRescanningSite(true);

    try {
      const createdRequestId = await requestEvaluationTargetRescan(targetId);
      for (let attempt = 0; attempt < RESCAN_RESULT_POLL_ATTEMPTS; attempt += 1) {
        if (attempt > 0) {
          await wait(RESCAN_RESULT_POLL_INTERVAL_MS);
        }

        const refreshedData = await loadDashboard({ awaitInFlight: true, clearOnError: false });
        const latestRequest =
          createdRequestId === null
            ? getLatestRequestForTarget(refreshedData ?? null, targetId)
            : refreshedData?.evaluationRequests.find((request) => request.id === createdRequestId) ?? null;

        if (!latestRequest) {
          continue;
        }

        const isCreatedOrUpdatedRequest =
          createdRequestId !== null ||
          previousLatestRequest === null ||
          latestRequest.id !== previousLatestRequest.id ||
          Date.parse(latestRequest.updatedAt) > Date.parse(previousLatestRequest.updatedAt);

        if (isCreatedOrUpdatedRequest && isFinalRequestStatus(latestRequest.status)) {
          break;
        }
      }
    } catch (error) {
      onError(getApiErrorMessage(error, "다시 스캔 요청 중 오류가 발생했습니다."));
    } finally {
      setIsRescanningSite(false);
    }
  }, [
    dashboardData,
    isRescanningSite,
    loadDashboard,
    onError,
    selectedEvaluationTargetModel,
    selectedOrganizationModel
  ]);

  return {
    handleRescanEvaluationTargetModel,
    isRescanningSite
  };
}
