package com.lab.monitor.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import lombok.*;

/**
 * Nested {@code agent} block in the ML server response.
 * Mirrors the on-device LLM judgment summary attached to each /analyze response.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
@JsonIgnoreProperties(ignoreUnknown = true)
public class AgentJudgmentDto {
    private String judgment;
    private String severity;
    private String reason;
    private String action;
    private String hwDegradation;
    /** Mock vs. real agent flag. Snake-case {@code is_mock} auto-mapped via JsonNaming. */
    private Boolean isMock;
    /** Model name (e.g. "mock", "claude-sonnet-...") used as fallback when isMock is null. */
    private String modelName;
}
