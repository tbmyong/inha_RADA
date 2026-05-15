package com.lab.monitor.entity;

import io.hypersistence.utils.hibernate.type.json.JsonBinaryType;
import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.Type;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

@Entity
@Table(name = "anomaly_history")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class AnomalyHistory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "pc_id", length = 64, nullable = false)
    private String pcId;

    @Column(name = "detected_at", nullable = false)
    private OffsetDateTime detectedAt;

    @Column(name = "severity", length = 16, nullable = false)
    private String severity;

    @Column(name = "anomaly_type", length = 64)
    private String anomalyType;

    @Column(name = "message", columnDefinition = "text")
    private String message;

    @Type(JsonBinaryType.class)
    @Column(name = "scores", columnDefinition = "jsonb")
    private Map<String, Object> scores;

    @Type(JsonBinaryType.class)
    @Column(name = "alerts", columnDefinition = "jsonb")
    private List<Map<String, Object>> alerts;
}
