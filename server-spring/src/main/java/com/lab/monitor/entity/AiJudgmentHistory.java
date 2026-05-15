package com.lab.monitor.entity;

import io.hypersistence.utils.hibernate.type.json.JsonBinaryType;
import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.Type;

import java.time.OffsetDateTime;
import java.util.Map;

@Entity
@Table(name = "ai_judgment_history")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class AiJudgmentHistory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "pc_id", length = 64, nullable = false)
    private String pcId;

    @Column(name = "judged_at", nullable = false)
    private OffsetDateTime judgedAt;

    @Column(name = "anomaly_id")
    private Long anomalyId;

    @Column(name = "model_name", length = 64)
    private String modelName;

    @Column(name = "verdict", length = 32)
    private String verdict;

    @Column(name = "confidence")
    private Double confidence;

    // V5 spec-aligned columns (mirror ML agent payload directly)
    @Column(name = "judgment", length = 64)
    private String judgment;

    @Column(name = "severity", length = 16)
    private String severity;

    @Column(name = "reason", columnDefinition = "text")
    private String reason;

    @Column(name = "action", columnDefinition = "text")
    private String action;

    @Column(name = "is_mock")
    private Boolean isMock;

    @Type(JsonBinaryType.class)
    @Column(name = "details", columnDefinition = "jsonb")
    private Map<String, Object> details;
}
