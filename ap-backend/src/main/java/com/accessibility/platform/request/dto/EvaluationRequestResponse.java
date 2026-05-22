package com.accessibility.platform.request.dto;

import com.accessibility.platform.request.domain.EvaluationRequest;
import com.accessibility.platform.request.domain.EvaluationRequestStatus;

import java.time.LocalDateTime;

public record EvaluationRequestResponse(
    Long id,
    Long evaluationTargetId,
    String targetName,
    EvaluationRequestStatus status,
    String requestNote,
    LocalDateTime requestedAt,
    LocalDateTime createdAt,
    LocalDateTime updatedAt
) {
    public static EvaluationRequestResponse from(EvaluationRequest request) {
        return new EvaluationRequestResponse(
            request.getId(),
            request.getEvaluationTarget().getId(),
            request.getEvaluationTarget().getName(),
            request.getStatus(),
            request.getRequestNote(),
            request.getRequestedAt(),
            request.getCreatedAt(),
            request.getUpdatedAt()
        );
    }
}
