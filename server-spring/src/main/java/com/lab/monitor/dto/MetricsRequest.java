package com.lab.monitor.dto;

import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import jakarta.validation.constraints.NotNull;
import lombok.*;

import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Agent -> Server metrics payload.
 *
 * Real Agent payload is snake_case with exactly 22 keys (per Agent v1.x spec).
 * - 5 surface metrics map to operational columns on metrics_history
 *   (timestamp, cpu_percent, memory_percent, inbound_mb, outbound_mb).
 * - The remaining 17 keys are explicitly typed here so deserialization is
 *   exhaustive and downstream code can preserve them in metrics_history.extra
 *   (jsonb).
 * - {@code extra} is also a {@link JsonAnySetter} catch-all so future Agent
 *   keys are not silently dropped.
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class MetricsRequest {

    // 1. pc_id
    private String pcId;

    // 2. timestamp -> Entity.collectedAt
    @NotNull
    private OffsetDateTime timestamp;

    // 3. cpu_percent -> Entity.cpuPercent
    private Double cpuPercent;

    // 4. cpu_core_count
    private Integer cpuCoreCount;

    // 5. memory_percent -> Entity.memPercent
    private Double memoryPercent;

    // 6. memory_used_gb
    private Double memoryUsedGb;

    // 7. memory_total_gb
    private Double memoryTotalGb;

    // 8. disk_read_mb -> Entity.diskReadMb (dedicated column)
    private Double diskReadMb;

    // 9. disk_write_mb -> Entity.diskWriteMb (dedicated column)
    private Double diskWriteMb;

    // 10. inbound_mb -> Entity.inboundMb
    private Double inboundMb;

    // 11. outbound_mb -> Entity.outboundMb
    private Double outboundMb;

    // 12. inbound_total_mb
    private Double inboundTotalMb;

    // 13. outbound_total_mb
    private Double outboundTotalMb;

    // 14. external_packet_count
    private Long externalPacketCount;

    // 15. external_connection_count
    private Long externalConnectionCount;

    // 16. external_connections
    private List<Map<String, Object>> externalConnections;

    // 17. active_ports
    private List<Integer> activePorts;

    // 18. gpu
    private Map<String, Object> gpu;

    // 19. top_processes
    private List<Map<String, Object>> topProcesses;

    // 20. loop_elapsed
    private Double loopElapsed;

    // 21. local_alerts
    private List<Map<String, Object>> localAlerts;

    // 22. boxplot_signal
    private Map<String, Object> boxplotSignal;

    // catch-all for any future Agent keys not explicitly modeled above
    @Builder.Default
    private Map<String, Object> extra = new LinkedHashMap<>();

    @JsonAnySetter
    public void putExtra(String key, Object value) {
        if (extra == null) {
            extra = new LinkedHashMap<>();
        }
        extra.put(key, value);
    }

    @JsonAnyGetter
    public Map<String, Object> getExtra() {
        return extra;
    }
}
