package com.lab.monitor.service;

import com.lab.monitor.dto.MetricsRequest;
import com.lab.monitor.entity.MetricsHistory;
import com.lab.monitor.repository.MetricsRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class MetricsServiceTest {

    private MetricsRepository metricsRepository;
    private MlForwardService mlForwardService;
    private MetricsService service;

    @BeforeEach
    void setUp() {
        metricsRepository = mock(MetricsRepository.class);
        mlForwardService = mock(MlForwardService.class);
        service = new MetricsService(metricsRepository, mlForwardService);
    }

    @Test
    void ingest_persists_operational_columns_and_preserves_extra_keys() {
        MetricsRequest req = MetricsRequest.builder()
                .pcId("payload-pc")
                .timestamp(OffsetDateTime.now())
                .cpuPercent(50.0)
                .cpuCoreCount(8)
                .memoryPercent(60.0)
                .memoryUsedGb(12.0)
                .memoryTotalGb(16.0)
                // disk read/write are now stored verbatim in dedicated columns
                .diskReadMb(35.0)
                .diskWriteMb(36.0)
                .inboundMb(100.0)
                .outboundMb(200.0)
                .inboundTotalMb(1000.0)
                .outboundTotalMb(2000.0)
                .externalPacketCount(500L)
                .externalConnectionCount(3L)
                .externalConnections(List.of(Map.of("remote", "1.2.3.4:80", "state", "ESTABLISHED")))
                .activePorts(List.of(80, 443))
                .gpu(Map.of(
                        "available", true,
                        "load_percent", 22.7,
                        "memory_used_mb", 4096.0,
                        "temperature", 55.0))
                .topProcesses(List.of(Map.of("pid", 1234, "name", "java")))
                .loopElapsed(0.21)
                .localAlerts(List.of())
                .boxplotSignal(Map.of("cpu_iqr_outlier", false))
                .build();
        when(metricsRepository.save(any(MetricsHistory.class)))
                .thenAnswer(inv -> {
                    MetricsHistory m = inv.getArgument(0);
                    m.setId(1L);
                    return m;
                });

        MetricsHistory result = service.ingest(req, "pc-1");

        ArgumentCaptor<MetricsHistory> cap = ArgumentCaptor.forClass(MetricsHistory.class);
        verify(metricsRepository).save(cap.capture());
        MetricsHistory saved = cap.getValue();

        // 1:1 operational column mapping (new field names)
        assertEquals("pc-1", saved.getPcId());
        assertEquals(50.0, saved.getCpuPercent());
        assertEquals(60.0, saved.getMemPercent());
        assertEquals(35.0, saved.getDiskReadMb());
        assertEquals(36.0, saved.getDiskWriteMb());
        assertEquals(100.0, saved.getInboundMb());
        assertEquals(200.0, saved.getOutboundMb());
        // GPU columns promoted from the gpu sub-map
        assertEquals(22.7, saved.getGpuPercent());
        assertEquals(4096.0, saved.getVramMb());
        assertNotNull(saved.getCollectedAt());

        // extra (jsonb) preserves the non-operational keys.
        // Promoted keys (disk_read_mb, disk_write_mb, gpu_percent core
        // fields) are NOT duplicated in extra anymore.
        Map<String, Object> extra = saved.getExtra();
        assertNotNull(extra);
        assertEquals("payload-pc", extra.get("payload_pc_id"));
        assertEquals(8, extra.get("cpu_core_count"));
        assertEquals(12.0, extra.get("memory_used_gb"));
        assertEquals(16.0, extra.get("memory_total_gb"));
        assertFalse(extra.containsKey("disk_read_mb"),
                "disk_read_mb promoted to column; must not duplicate in extra");
        assertFalse(extra.containsKey("disk_write_mb"),
                "disk_write_mb promoted to column; must not duplicate in extra");
        assertEquals(1000.0, extra.get("inbound_total_mb"));
        assertEquals(2000.0, extra.get("outbound_total_mb"));
        assertEquals(500L, extra.get("external_packet_count"));
        assertEquals(3L, extra.get("external_connection_count"));
        assertNotNull(extra.get("external_connections"));
        assertNotNull(extra.get("active_ports"));
        // gpu sub-map preserved whole so non-promoted fields (temperature)
        // are still recoverable.
        assertNotNull(extra.get("gpu"));
        assertNotNull(extra.get("top_processes"));
        assertEquals(0.21, extra.get("loop_elapsed"));
        assertNotNull(extra.get("local_alerts"));
        assertNotNull(extra.get("boxplot_signal"));

        assertEquals(1L, result.getId());
    }

    @Test
    void ingest_delegates_to_forwardAsync() {
        MetricsRequest req = MetricsRequest.builder()
                .timestamp(OffsetDateTime.now())
                .cpuPercent(10.0)
                .build();
        when(metricsRepository.save(any(MetricsHistory.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        service.ingest(req, "pc-2");

        verify(mlForwardService).forwardAsync(eq("pc-2"), eq(req));
    }

    @Test
    void ingest_saves_before_forwardAsync() {
        MetricsRequest req = MetricsRequest.builder()
                .timestamp(OffsetDateTime.now())
                .cpuPercent(10.0)
                .build();
        when(metricsRepository.save(any(MetricsHistory.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        service.ingest(req, "pc-3");

        InOrder inOrder = inOrder(metricsRepository, mlForwardService);
        inOrder.verify(metricsRepository).save(any(MetricsHistory.class));
        inOrder.verify(mlForwardService).forwardAsync(eq("pc-3"), eq(req));
    }

    @Test
    void disk_pair_stored_verbatim_when_both_null() {
        MetricsRequest req = MetricsRequest.builder()
                .timestamp(OffsetDateTime.now())
                .cpuPercent(1.0)
                .build();
        when(metricsRepository.save(any(MetricsHistory.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        service.ingest(req, "pc-d1");

        ArgumentCaptor<MetricsHistory> cap = ArgumentCaptor.forClass(MetricsHistory.class);
        verify(metricsRepository).save(cap.capture());
        assertNull(cap.getValue().getDiskReadMb());
        assertNull(cap.getValue().getDiskWriteMb());
    }

    @Test
    void disk_pair_stored_verbatim_when_only_read_set() {
        MetricsRequest req = MetricsRequest.builder()
                .timestamp(OffsetDateTime.now())
                .diskReadMb(10.0)
                .build();
        when(metricsRepository.save(any(MetricsHistory.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        service.ingest(req, "pc-d2");

        ArgumentCaptor<MetricsHistory> cap = ArgumentCaptor.forClass(MetricsHistory.class);
        verify(metricsRepository).save(cap.capture());
        assertEquals(10.0, cap.getValue().getDiskReadMb());
        assertNull(cap.getValue().getDiskWriteMb());
    }

    @Test
    void gpu_percent_falls_back_to_sm_percent_when_load_percent_absent() {
        MetricsRequest req = MetricsRequest.builder()
                .timestamp(OffsetDateTime.now())
                .gpu(Map.of("sm_percent", 71.0))
                .build();
        when(metricsRepository.save(any(MetricsHistory.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        service.ingest(req, "pc-g1");

        ArgumentCaptor<MetricsHistory> cap = ArgumentCaptor.forClass(MetricsHistory.class);
        verify(metricsRepository).save(cap.capture());
        assertEquals(71.0, cap.getValue().getGpuPercent());
    }

    @Test
    void gpu_columns_null_when_gpu_sub_map_absent() {
        MetricsRequest req = MetricsRequest.builder()
                .timestamp(OffsetDateTime.now())
                .build();
        when(metricsRepository.save(any(MetricsHistory.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        service.ingest(req, "pc-g2");

        ArgumentCaptor<MetricsHistory> cap = ArgumentCaptor.forClass(MetricsHistory.class);
        verify(metricsRepository).save(cap.capture());
        assertNull(cap.getValue().getGpuPercent());
        assertNull(cap.getValue().getVramMb());
    }

    @Test
    void pcId_mismatch_header_wins_and_payload_pcId_is_overwritten() {
        MetricsRequest req = MetricsRequest.builder()
                .pcId("body-pc")
                .timestamp(OffsetDateTime.now())
                .cpuPercent(1.0)
                .build();
        when(metricsRepository.save(any(MetricsHistory.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        service.ingest(req, "header-pc");

        ArgumentCaptor<MetricsHistory> cap = ArgumentCaptor.forClass(MetricsHistory.class);
        verify(metricsRepository).save(cap.capture());
        // entity uses header
        assertEquals("header-pc", cap.getValue().getPcId());
        // DTO has been mutated so ML forward sees the authoritative value
        assertEquals("header-pc", req.getPcId());
        // ML forward is invoked with the authoritative header pcId
        verify(mlForwardService).forwardAsync(eq("header-pc"), eq(req));
    }

    @Test
    void pcId_match_does_not_warn_and_passes_through() {
        MetricsRequest req = MetricsRequest.builder()
                .pcId("pc-1")
                .timestamp(OffsetDateTime.now())
                .cpuPercent(1.0)
                .build();
        when(metricsRepository.save(any(MetricsHistory.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        service.ingest(req, "pc-1");

        ArgumentCaptor<MetricsHistory> cap = ArgumentCaptor.forClass(MetricsHistory.class);
        verify(metricsRepository).save(cap.capture());
        assertEquals("pc-1", cap.getValue().getPcId());
    }

    @Test
    void ingest_preserves_derived_features_in_extra_via_jsonAnySetter_path() {
        // Simulate what Jackson does for an unknown top-level key: putExtra()
        // routes "derived_features" into the catch-all map. MetricsService
        // must propagate it verbatim into metrics_history.extra.
        Map<String, Object> derived = new java.util.LinkedHashMap<>();
        derived.put("cpu_mem_ratio", 1.229);
        derived.put("net_io_ratio", 1.564);
        derived.put("disk_io_total", 3.6);
        derived.put("cpu_zscore", 1.85);
        derived.put("mem_zscore", 1.42);
        derived.put("inbound_rate_ema", 12000.5);
        derived.put("outbound_rate_ema", 7500.2);
        derived.put("external_pkt_rate", 41.13);
        derived.put("gpu_load_ema", 21.5);
        derived.put("process_cpu_share_top1", 0.452);
        derived.put("anomaly_score", 0.73);
        derived.put("trend_slope_cpu", 0.05);
        derived.put("trend_slope_mem", 0.02);

        MetricsRequest req = MetricsRequest.builder()
                .timestamp(OffsetDateTime.now())
                .cpuPercent(50.0)
                .build();
        // Route through the same @JsonAnySetter that Jackson would use.
        req.putExtra("derived_features", derived);

        when(metricsRepository.save(any(MetricsHistory.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        service.ingest(req, "pc-df-1");

        ArgumentCaptor<MetricsHistory> cap = ArgumentCaptor.forClass(MetricsHistory.class);
        verify(metricsRepository).save(cap.capture());
        Map<String, Object> extra = cap.getValue().getExtra();

        assertNotNull(extra);
        assertTrue(extra.containsKey("derived_features"),
                "derived_features must be preserved into metrics_history.extra");
        Object df = extra.get("derived_features");
        assertTrue(df instanceof Map, "derived_features must remain a Map");
        @SuppressWarnings("unchecked")
        Map<String, Object> got = (Map<String, Object>) df;
        assertEquals(13, got.size());
        assertEquals(0.73, got.get("anomaly_score"));
        assertEquals(1.229, got.get("cpu_mem_ratio"));
    }

    @Test
    void buildExtra_preserves_payload_pc_id_but_omits_promoted_disk_keys() {
        MetricsRequest req = MetricsRequest.builder()
                .pcId("payload-only-pc")
                .timestamp(OffsetDateTime.now())
                .diskReadMb(3.0)
                .diskWriteMb(4.0)
                .build();
        when(metricsRepository.save(any(MetricsHistory.class)))
                .thenAnswer(inv -> inv.getArgument(0));

        service.ingest(req, "header-pc");

        ArgumentCaptor<MetricsHistory> cap = ArgumentCaptor.forClass(MetricsHistory.class);
        verify(metricsRepository).save(cap.capture());
        MetricsHistory saved = cap.getValue();

        // header pcId is authoritative for the entity column
        assertEquals("header-pc", saved.getPcId());
        // disk pair is now in dedicated columns
        assertEquals(3.0, saved.getDiskReadMb());
        assertEquals(4.0, saved.getDiskWriteMb());

        Map<String, Object> extra = saved.getExtra();
        assertNotNull(extra);
        // payload-side pc_id preserved separately
        assertEquals("payload-only-pc", extra.get("payload_pc_id"));
        // promoted columns must not duplicate into extra
        assertFalse(extra.containsKey("disk_read_mb"));
        assertFalse(extra.containsKey("disk_write_mb"));
    }
}
