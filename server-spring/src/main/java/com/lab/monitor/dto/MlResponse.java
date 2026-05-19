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
    /**
     * Free-form retrieval evidence block emitted by the ML server (snake: {@code retrieval_evidence}).
     * Includes {@code top_k} (list of past similar segments with distance/past_verdict/timestamp),
     * peer_mismatch flag, retrieval_score, novelty, similar_*_count buckets, etc.
     * Persisted verbatim into {@code anomaly_history.scores->'retrieval_evidence'} for audit.
     * May be null on older ML deployments.
     */
    private Map<String, Object> retrievalEvidence;
    /**
     * F5: signals that could not be collected on the client (e.g. "network", "process",
     * "derived_features"). Empty list / null on healthy collection. Persisted into
     * {@code anomaly_history.scores->'signals_missing'} so silent-fail PCs are visible
     * in dashboards instead of being misread as "real zero" / NORMAL.
     */
    private List<String> signalsMissing;
}
