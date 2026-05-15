package com.lab.monitor.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.*;

import java.util.List;
import java.util.Map;

/**
 * ML server -> Server analysis response.
 *
 * Real ML payload is snake_case and centers on:
 *   - {@code overall_severity}: top-level severity (NORMAL / LOW / MEDIUM / HIGH ...)
 *   - {@code verdict}: human-facing label (SAFE / DANGEROUS / ...)
 *   - {@code agent}: nested on-device LLM judgment block
 *   - {@code scores}, {@code alerts}, {@code message}: pass-through diagnostics
 *
 * The earlier fields ({@code severity}, {@code anomalyType}, {@code modelName},
 * {@code confidence}) were not part of the actual ML contract and have been removed.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
@JsonIgnoreProperties(ignoreUnknown = true)
public class MlResponse {
    private String overallSeverity;
    private String verdict;
    private String message;
    private Map<String, Object> scores;
    private List<Map<String, Object>> alerts;
    private AgentJudgmentDto agent;
    /** Scoring policy version emitted by the ML server (snake: {@code policy_version}); may be null on older ML deployments. */
    private String policyVersion;
}
