package com.accessibility.platform.analysis.domain;

import com.accessibility.platform.common.entity.BaseTimeEntity;
import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(name = "issue_result")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class IssueResult extends BaseTimeEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "analysis_result_id", nullable = false)
    private AnalysisResult analysisResult;

    @Column(nullable = false, length = 100)
    private String issueCode;

    @Column(nullable = false, length = 200)
    private String issueTitle;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Severity severity;

    @Column(length = 500)
    private String locationPath;

    @Lob
    private String message;

    @Column(nullable = false)
    private boolean resolved;

    public IssueResult(AnalysisResult analysisResult, String issueCode, String issueTitle, Severity severity, String locationPath, String message) {
        this.analysisResult = analysisResult;
        this.issueCode = issueCode;
        this.issueTitle = issueTitle;
        this.severity = severity;
        this.locationPath = locationPath;
        this.message = message;
        this.resolved = false;
    }
}
