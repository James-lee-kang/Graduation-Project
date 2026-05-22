package com.accessibility.platform.request.service;

import com.accessibility.platform.common.exception.ResourceNotFoundException;
import com.accessibility.platform.request.domain.EvaluationRequest;
import com.accessibility.platform.request.dto.EvaluationRequestCreateRequest;
import com.accessibility.platform.request.dto.EvaluationRequestResponse;
import com.accessibility.platform.request.dto.EvaluationRequestStatusUpdateRequest;
import com.accessibility.platform.request.repository.EvaluationRequestRepository;
import com.accessibility.platform.target.domain.EvaluationTarget;
import com.accessibility.platform.target.service.EvaluationTargetService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class EvaluationRequestService {

    private final EvaluationRequestRepository evaluationRequestRepository;
    private final EvaluationTargetService evaluationTargetService;

    @Transactional
    public EvaluationRequestResponse create(EvaluationRequestCreateRequest request) {
        EvaluationTarget target = evaluationTargetService.getTarget(request.evaluationTargetId());
        EvaluationRequest evaluationRequest = new EvaluationRequest(target, request.requestNote());
        return EvaluationRequestResponse.from(evaluationRequestRepository.save(evaluationRequest));
    }

    public List<EvaluationRequestResponse> findAll() {
        return evaluationRequestRepository.findAll().stream()
                .map(EvaluationRequestResponse::from)
                .toList();
    }

    public EvaluationRequestResponse findById(Long id) {
        return EvaluationRequestResponse.from(getRequest(id));
    }

    @Transactional
    public EvaluationRequestResponse updateStatus(Long id, EvaluationRequestStatusUpdateRequest request) {
        EvaluationRequest evaluationRequest = getRequest(id);
        evaluationRequest.changeStatus(request.status());
        return EvaluationRequestResponse.from(evaluationRequest);
    }

    public EvaluationRequest getRequest(Long id) {
        return evaluationRequestRepository.findById(id)
                .orElseThrow(ResourceNotFoundException::new);
    }
}
