package com.lab.monitor.service;

import com.lab.monitor.dto.MetricsRequest;
import com.lab.monitor.entity.MetricsHistory;
import com.lab.monitor.repository.MetricsRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.LinkedHashMap;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class MetricsService {

    private final MetricsRepository metricsRepository;
    private final MlForwardService mlForwardService;

    @Transactional
    public MetricsHistory ingest(MetricsRequest req, String pcId) {
        // pc_id policy: the header-derived pcId is authoritative. On mismatch we
        // log a WARN, retain the original body pc_id under extra.payload_pc_id for
        // forensics (via buildExtra below), then overwrite the DTO so the ML
        // forward and the entity column see the authoritative value.
        String bodyPcId = req.getPcId();
        if (bodyPcId != null && !bodyPcId.equals(pcId)) {
            // Client 가 MAC 기반 pc_id 를 보내는 경우 정상 흐름.
            // API key 가 binding 한 header pc_id 가 truth source.
            log.debug("pcId override: header={} body={}, using header", pcId, bodyPcId);
        }
        req.setPcId(pcId);
        MetricsHistory entity = MetricsHistory.builder()
                .pcId(pcId)
                .collectedAt(req.getTimestamp())
                .cpuPercent(req.getCpuPercent())
                .memPercent(req.getMemoryPercent())
                .diskReadMb(req.getDiskReadMb())
                .diskWriteMb(req.getDiskWriteMb())
                .inboundMb(req.getInboundMb())
                .outboundMb(req.getOutboundMb())
                .gpuPercent(extractGpuPercent(req.getGpu()))
                .vramMb(extractVramMb(req.getGpu()))
                .extra(buildExtra(req, bodyPcId))
                .build();
        MetricsHistory saved = metricsRepository.save(entity);
        mlForwardService.forwardAsync(pcId, req);
        return saved;
    }

    /**
     * Extracts overall GPU load percent from the raw gpu sub-map.
     * Real Agent (client_core.collector.gpu.GpuCollector) ships {@code load_percent}
     * as the GPUtil-derived 0-100 load reading; {@code sm_percent} is a fallback
     * synonym some experimental builds emit. Returns null when neither is present
     * or the value is not numeric.
     */
    static Double extractGpuPercent(Map<String, Object> gpu) {
        if (gpu == null) return null;
        Object v = gpu.get("load_percent");
        if (v == null) v = gpu.get("sm_percent");
        return toDouble(v);
    }

    /**
     * Extracts used VRAM in MB from the raw gpu sub-map.
     * Real Agent emits {@code memory_used_mb}; {@code vram_used_mb} / {@code vram_mb}
     * are accepted as fallbacks for forward compatibility.
     */
    static Double extractVramMb(Map<String, Object> gpu) {
        if (gpu == null) return null;
        Object v = gpu.get("memory_used_mb");
        if (v == null) v = gpu.get("vram_used_mb");
        if (v == null) v = gpu.get("vram_mb");
        return toDouble(v);
    }

    private static Double toDouble(Object v) {
        if (v == null) return null;
        if (v instanceof Number n) return n.doubleValue();
        try {
            return Double.parseDouble(v.toString());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    /**
     * Bundles the residual non-operational Agent keys into the
     * metrics_history.extra jsonb column. Operational columns
     * (timestamp, cpu_percent, mem_percent, inbound_mb, outbound_mb,
     * disk_read_mb, disk_write_mb, gpu_percent, vram_mb, pc_id) are
     * promoted to dedicated DB columns and are NOT duplicated here.
     *
     * The full original gpu sub-map is still preserved here so non-promoted
     * fields (temperature, power_draw_w, tensor_core_active, etc.) survive.
     */
    private Map<String, Object> buildExtra(MetricsRequest req, String originalBodyPcId) {
        Map<String, Object> out = new LinkedHashMap<>();
        // pc_id from payload (pre-header-override) preserved here for forensics.
        // Header pcId is authoritative for the entity column.
        putIfNotNull(out, "payload_pc_id", originalBodyPcId);
        putIfNotNull(out, "cpu_core_count", req.getCpuCoreCount());
        putIfNotNull(out, "memory_used_gb", req.getMemoryUsedGb());
        putIfNotNull(out, "memory_total_gb", req.getMemoryTotalGb());
        putIfNotNull(out, "inbound_total_mb", req.getInboundTotalMb());
        putIfNotNull(out, "outbound_total_mb", req.getOutboundTotalMb());
        putIfNotNull(out, "external_packet_count", req.getExternalPacketCount());
        putIfNotNull(out, "external_connection_count", req.getExternalConnectionCount());
        putIfNotNull(out, "external_connections", req.getExternalConnections());
        putIfNotNull(out, "active_ports", req.getActivePorts());
        // gpu sub-map preserved as-is for any non-promoted fields (temperature, power...)
        putIfNotNull(out, "gpu", req.getGpu());
        putIfNotNull(out, "top_processes", req.getTopProcesses());
        putIfNotNull(out, "loop_elapsed", req.getLoopElapsed());
        putIfNotNull(out, "local_alerts", req.getLocalAlerts());
        putIfNotNull(out, "boxplot_signal", req.getBoxplotSignal());
        // Forward-compatibility: any unknown keys captured by @JsonAnySetter
        Map<String, Object> any = req.getExtra();
        if (any != null && !any.isEmpty()) {
            out.putAll(any);
        }
        return out;
    }

    private void putIfNotNull(Map<String, Object> m, String k, Object v) {
        if (v != null) {
            m.put(k, v);
        }
    }
}
