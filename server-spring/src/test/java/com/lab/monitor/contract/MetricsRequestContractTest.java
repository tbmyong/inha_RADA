package com.lab.monitor.contract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.lab.monitor.dto.MetricsRequest;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Contract test for the Agent -> Server metrics payload.
 *
 * Real Agent v1.x payload is snake_case with exactly 22 top-level keys. All 22 must
 * deserialize into explicit, typed fields on {@link MetricsRequest}. The
 * {@code extra} catch-all (via @JsonAnySetter) must remain empty for the canonical
 * fixture, since every documented key is modeled. Unknown future keys are still
 * captured in {@code extra} for forward-compatibility.
 */
class MetricsRequestContractTest {

    private final ObjectMapper mapper = new ObjectMapper().registerModule(new JavaTimeModule());

    private byte[] read(String path) throws IOException {
        try (InputStream is = getClass().getResourceAsStream(path)) {
            assertThat(is).as("fixture present: " + path).isNotNull();
            return is.readAllBytes();
        }
    }

    @Test
    void agent_22key_payload_has_22_top_level_keys() throws IOException {
        byte[] bytes = read("/fixtures/agent/payload_22keys.json");
        JsonNode raw = mapper.readTree(bytes);

        java.util.Iterator<String> it = raw.fieldNames();
        int count = 0;
        while (it.hasNext()) { it.next(); count++; }
        assertThat(count).isEqualTo(22);
    }

    @Test
    void agent_payload_maps_exhaustively_to_dto() throws IOException {
        byte[] bytes = read("/fixtures/agent/payload_22keys.json");

        MetricsRequest dto = mapper.readValue(bytes, MetricsRequest.class);

        // 1-2. identification + timestamp
        assertThat(dto.getPcId()).isEqualTo("pc-fixture-001");
        assertThat(dto.getTimestamp()).isNotNull();

        // 3-7. cpu + memory scalars
        assertThat(dto.getCpuPercent()).isEqualTo(87.5);
        assertThat(dto.getCpuCoreCount()).isEqualTo(8);
        assertThat(dto.getMemoryPercent()).isEqualTo(71.2);
        assertThat(dto.getMemoryUsedGb()).isEqualTo(12.5);
        assertThat(dto.getMemoryTotalGb()).isEqualTo(16.0);

        // 8-9. disk read/write (raw, summed downstream into Entity.diskUsage)
        assertThat(dto.getDiskReadMb()).isEqualTo(1.5);
        assertThat(dto.getDiskWriteMb()).isEqualTo(2.1);

        // 10-13. network MB (rate + total)
        assertThat(dto.getInboundMb()).isEqualTo(12345.6);
        assertThat(dto.getOutboundMb()).isEqualTo(7890.1);
        assertThat(dto.getInboundTotalMb()).isEqualTo(50000.0);
        assertThat(dto.getOutboundTotalMb()).isEqualTo(30000.0);

        // 14-15. external counters
        assertThat(dto.getExternalPacketCount()).isEqualTo(1234L);
        assertThat(dto.getExternalConnectionCount()).isEqualTo(5L);

        // 16. external_connections list
        List<Map<String, Object>> conns = dto.getExternalConnections();
        assertThat(conns).hasSize(1);

        // 17. active_ports list
        assertThat(dto.getActivePorts()).containsExactly(80, 443, 22);

        // 18. gpu map
        assertThat(dto.getGpu()).isNotNull();
        assertThat(dto.getGpu()).isInstanceOf(Map.class);

        // 19. top_processes
        assertThat(dto.getTopProcesses()).hasSize(1);

        // 20. loop_elapsed
        assertThat(dto.getLoopElapsed()).isEqualTo(0.21);

        // 21. local_alerts (empty list still mapped)
        assertThat(dto.getLocalAlerts()).isEmpty();

        // 22. boxplot_signal
        assertThat(dto.getBoxplotSignal()).isNotNull();
        assertThat(dto.getBoxplotSignal()).isInstanceOf(Map.class);

        // catch-all is empty (every fixture key is explicitly modeled)
        assertThat(dto.getExtra()).isEmpty();
    }

    @Test
    void derived_features_payload_is_captured_in_extra() throws IOException {
        byte[] bytes = read("/fixtures/agent/payload_with_derived_features.json");

        MetricsRequest dto = mapper.readValue(bytes, MetricsRequest.class);

        // The 22 documented top-level keys still map exhaustively to typed fields.
        assertThat(dto.getPcId()).isEqualTo("pc-fixture-002");
        assertThat(dto.getCpuPercent()).isEqualTo(87.5);
        assertThat(dto.getBoxplotSignal()).isNotNull();

        // derived_features is NOT an explicit DTO field (Option A) -> it must
        // land in the @JsonAnySetter catch-all so MetricsService.buildExtra
        // propagates it verbatim into metrics_history.extra (jsonb).
        Map<String, Object> extra = dto.getExtra();
        assertThat(extra).containsKey("derived_features");
        Object df = extra.get("derived_features");
        assertThat(df).isInstanceOf(Map.class);

        @SuppressWarnings("unchecked")
        Map<String, Object> derived = (Map<String, Object>) df;
        // C-team plan: 13 derived feature keys.
        assertThat(derived).hasSize(13);
        assertThat(derived).containsKeys(
                "cpu_mem_ratio", "net_io_ratio", "disk_io_total",
                "cpu_zscore", "mem_zscore",
                "inbound_rate_ema", "outbound_rate_ema",
                "external_pkt_rate", "gpu_load_ema",
                "process_cpu_share_top1",
                "anomaly_score", "trend_slope_cpu", "trend_slope_mem");
        assertThat(derived.get("anomaly_score")).isEqualTo(0.73);
    }

    @Test
    void unknown_future_key_is_captured_by_extra_catchall() throws IOException {
        String json = "{\"timestamp\":\"2026-05-07T01:23:45Z\"," +
                "\"cpu_percent\":1.0," +
                "\"future_metric\":\"surprise\"}";
        MetricsRequest dto = mapper.readValue(json, MetricsRequest.class);
        assertThat(dto.getCpuPercent()).isEqualTo(1.0);
        assertThat(dto.getExtra()).containsEntry("future_metric", "surprise");
    }
}
