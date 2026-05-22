package com.accessibility.platform.request.repository;

import com.accessibility.platform.request.domain.EvaluationRequest;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface EvaluationRequestRepository extends JpaRepository<EvaluationRequest, Long> {
    List<EvaluationRequest> findByEvaluationTargetId(Long evaluationTargetId);
}
