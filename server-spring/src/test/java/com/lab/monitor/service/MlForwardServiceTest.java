package com.lab.monitor.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.lab.monitor.dto.MetricsRequest;
import com.lab.monitor.dto.MlResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

import java.time.OffsetDateTime;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class MlForwardServiceTest {

    private WebClient mlWebClient;
    private AlertService alertService;
    private MlForwardService service;

    @BeforeEach
    void setUp() {
        mlWebClient = mock(WebClient.class);
        alertService = mock(AlertService.class);
        service = new MlForwardService(mlWebClient, alertService);
    }

    @Test
    void forwardAsync_invokes_alertService_when_response_present() {
        MetricsRequest req = MetricsRequest.builder()
                .timestamp(OffsetDateTime.now())
                .cpuPercent(80.0)
                .build();
        MlResponse resp = MlResponse.builder().overallSeverity("HIGH").build();

        MlForwardService spy = spy(service);
        doReturn(Optional.of(resp)).when(spy).forward(eq("pc-1"), eq(req));

        spy.forwardAsync("pc-1", req);

        verify(alertService).handle(eq(resp), eq("pc-1"));
    }

    @Test
    void forwardAsync_skips_alertService_when_response_empty() {
        MetricsRequest req = MetricsRequest.builder()
                .timestamp(OffsetDateTime.now())
                .cpuPercent(80.0)
                .build();

        MlForwardService spy = spy(service);
        doReturn(Optional.empty()).when(spy).forward(eq("pc-1"), eq(req));

        spy.forwardAsync("pc-1", req);

        verify(alertService, never()).handle(any(), any());
    }

    @Test
    void forwardAsync_swallows_exception_from_forward() {
        MetricsRequest req = MetricsRequest.builder()
                .timestamp(OffsetDateTime.now())
                .cpuPercent(80.0)
                .build();

        MlForwardService spy = spy(service);
        doThrow(new RuntimeException("boom")).when(spy).forward(eq("pc-1"), eq(req));

        spy.forwardAsync("pc-1", req);

        verify(alertService, never()).handle(any(), any());
    }

    @Test
    void serialized_payload_uses_snake_case_and_flat_structure() throws Exception {
        MetricsRequest req = MetricsRequest.builder()
                .pcId("pc-1")
                .timestamp(OffsetDateTime.parse("2025-01-01T00:00:00Z"))
                .cpuPercent(80.0)
                .memoryPercent(50.0)
                .build();

        ObjectMapper mapper = new ObjectMapper().registerModule(new JavaTimeModule());
        JsonNode node = mapper.valueToTree(req);

        // snake_case keys present at the top level (flat structure)
        assertThat(node.has("pc_id")).isTrue();
        assertThat(node.has("cpu_percent")).isTrue();
        assertThat(node.has("timestamp")).isTrue();
        assertThat(node.has("memory_percent")).isTrue();

        // wrapper keys (camelCase pcId / metrics) must not exist
        assertThat(node.has("pcId")).isFalse();
        assertThat(node.has("metrics")).isFalse();
        assertThat(node.get("pc_id").asText()).isEqualTo("pc-1");
    }
}
