package com.lab.monitor.entity;

import io.hypersistence.utils.hibernate.type.json.JsonBinaryType;
import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.Type;

import java.time.OffsetDateTime;
import java.util.Map;

@Entity
@Table(name = "metrics_history")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class MetricsHistory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "pc_id", length = 64, nullable = false)
    private String pcId;

    @Column(name = "collected_at", nullable = false)
    private OffsetDateTime collectedAt;

    @Column(name = "cpu_percent")
    private Double cpuPercent;

    @Column(name = "mem_percent")
    private Double memPercent;

    @Column(name = "disk_read_mb")
    private Double diskReadMb;

    @Column(name = "disk_write_mb")
    private Double diskWriteMb;

    @Column(name = "inbound_mb")
    private Double inboundMb;

    @Column(name = "outbound_mb")
    private Double outboundMb;

    @Column(name = "gpu_percent")
    private Double gpuPercent;

    @Column(name = "vram_mb")
    private Double vramMb;

    @Type(JsonBinaryType.class)
    @Column(name = "extra", columnDefinition = "jsonb")
    private Map<String, Object> extra;
}
