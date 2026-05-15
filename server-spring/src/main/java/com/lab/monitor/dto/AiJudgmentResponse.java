package com.lab.monitor.dto;

import com.lab.monitor.entity.AiJudgmentHistory;
import lombok.*;

import java.time.OffsetDateTime;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class AiJudgmentResponse {
    private Long id;
    private String pcId;
    private OffsetDateTime judgedAt;
    private Long anomalyId;
    private String judgment;
    private String severity;
    private String reason;
    private String action;
    private Boolean isMock;
    private String modelName;

    public static AiJudgmentResponse from(AiJudgmentHistory a) {
        return AiJudgmentResponse.builder()
                .id(a.getId())
                .pcId(a.getPcId())
                .judgedAt(a.getJudgedAt())
                .anomalyId(a.getAnomalyId())
                .judgment(a.getJudgment())
                .severity(a.getSeverity())
                .reason(a.getReason())
                .action(a.getAction())
                .isMock(a.getIsMock())
                .modelName(a.getModelName())
                .build();
    }
}
