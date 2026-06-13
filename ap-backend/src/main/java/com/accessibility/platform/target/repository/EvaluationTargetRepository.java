package com.accessibility.platform.target.repository;

import com.accessibility.platform.target.domain.EvaluationTarget;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface EvaluationTargetRepository extends JpaRepository<EvaluationTarget, Long> {
    List<EvaluationTarget> findByOrganizationId(Long organizationId);
    Optional<EvaluationTarget> findByAccessUrl(String accessUrl);
}
