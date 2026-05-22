import { useCallback, useState } from "react";

import { createOrganizationModel, getApiErrorMessage } from "@/services/backend-api";

import type { LoadDashboard } from "./use-dashboard-data";

export function useOrganizationModelCreateForm({
  loadDashboard,
  onCreated
}: {
  loadDashboard: LoadDashboard;
  onCreated: () => void;
}) {
  const [isCreatingOrganizationModel, setIsCreatingOrganizationModel] = useState(false);
  const [isOrganizationCreateOpen, setIsOrganizationCreateOpen] = useState(false);
  const [newOrganizationModelName, setNewOrganizationModelName] = useState("");
  const [newOrganizationModelDescription, setNewOrganizationModelDescription] = useState("");
  const [projectCreateError, setProjectCreateError] = useState("");

  const openOrganizationCreateModal = useCallback(() => {
    setProjectCreateError("");
    setIsOrganizationCreateOpen(true);
  }, []);

  const handleCreateOrganizationModel = useCallback(async () => {
    const name = newOrganizationModelName.trim();
    if (name.length === 0) {
      setProjectCreateError("프로젝트 이름은 필수입니다.");
      return;
    }

    setIsCreatingOrganizationModel(true);
    setProjectCreateError("");

    try {
      await createOrganizationModel({
        name,
        description: newOrganizationModelDescription.trim()
      });

      await loadDashboard({ clearOnError: false });
      setNewOrganizationModelName("");
      setNewOrganizationModelDescription("");
      setIsOrganizationCreateOpen(false);
      onCreated();
    } catch (error) {
      setProjectCreateError(getApiErrorMessage(error, "프로젝트 생성 중 오류가 발생했습니다."));
    } finally {
      setIsCreatingOrganizationModel(false);
    }
  }, [loadDashboard, newOrganizationModelDescription, newOrganizationModelName, onCreated]);

  return {
    handleCreateOrganizationModel,
    isCreatingOrganizationModel,
    isOrganizationCreateOpen,
    newOrganizationModelDescription,
    newOrganizationModelName,
    openOrganizationCreateModal,
    projectCreateError,
    setIsOrganizationCreateOpen,
    setNewOrganizationModelDescription,
    setNewOrganizationModelName
  };
}
