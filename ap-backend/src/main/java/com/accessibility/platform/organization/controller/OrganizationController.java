package com.accessibility.platform.organization.controller;

import com.accessibility.platform.common.response.ApiResponse;
import com.accessibility.platform.organization.dto.OrganizationCreateRequest;
import com.accessibility.platform.organization.dto.OrganizationResponse;
import com.accessibility.platform.organization.dto.OrganizationUpdateRequest;
import com.accessibility.platform.organization.service.OrganizationService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/organizations")
public class OrganizationController {

    private final OrganizationService organizationService;

    @PostMapping
    public ApiResponse<OrganizationResponse> create(@Valid @RequestBody OrganizationCreateRequest request) {
        return ApiResponse.ok(organizationService.create(request));
    }

    @GetMapping
    public ApiResponse<List<OrganizationResponse>> findAll() {
        return ApiResponse.ok(organizationService.findAll());
    }

    @GetMapping("/{id}")
    public ApiResponse<OrganizationResponse> findById(@PathVariable Long id) {
        return ApiResponse.ok(organizationService.findById(id));
    }

    @PutMapping("/{id}")
    public ApiResponse<OrganizationResponse> update(
        @PathVariable Long id,
        @Valid @RequestBody OrganizationUpdateRequest request
    ) {
        return ApiResponse.ok(organizationService.update(id, request));
    }

    @PatchMapping("/{id}/deactivate")
    public ApiResponse<Void> deactivate(@PathVariable Long id) {
        organizationService.deactivate(id);
        return ApiResponse.ok(null, "기관이 비활성화되었습니다.");
    }
}
