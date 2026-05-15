package com.lab.monitor.dto;

import com.lab.monitor.entity.AnomalyHistory;
import lombok.*;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class AlertResponse {
    private Long id;
    private String pcId;
    private OffsetDateTime detectedAt;
    private String severity;
    private String anomalyType;
    private String message;
    private Map<String, Object> scores;
    private List<Map<String, Object>> alerts;

    public static AlertResponse from(AnomalyHistory a) {
        return AlertResponse.builder()
                .id(a.getId())
                .pcId(a.getPcId())
                .detectedAt(a.getDetectedAt())
                .severity(a.getSeverity())
                .anomalyType(a.getAnomalyType())
                .message(a.getMessage())
                .scores(a.getScores())
                .alerts(a.getAlerts())
                .build();
    }
}
