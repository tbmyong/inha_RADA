package com.lab.monitor.controller;

import com.lab.monitor.dto.MetricsRequest;
import com.lab.monitor.entity.MetricsHistory;
import com.lab.monitor.security.ApiKeyAuthFilter;
import com.lab.monitor.service.MetricsService;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.time.OffsetDateTime;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class MetricsControllerTest {

    private MetricsService metricsService;
    private MetricsController controller;

    @BeforeEach
    void setUp() {
        metricsService = mock(MetricsService.class);
        controller = new MetricsController(metricsService);
    }

    @Test
    void ingest_returns_accepted_with_pcId_from_request_attribute() {
        HttpServletRequest httpReq = mock(HttpServletRequest.class);
        when(httpReq.getAttribute(ApiKeyAuthFilter.PC_ID_ATTR)).thenReturn("pc-42");

        MetricsRequest req = MetricsRequest.builder()
                .timestamp(OffsetDateTime.now())
                .cpuPercent(10.0)
                .build();
        MetricsHistory saved = MetricsHistory.builder().id(7L).pcId("pc-42").build();
        when(metricsService.ingest(any(MetricsRequest.class), eq("pc-42"))).thenReturn(saved);

        ResponseEntity<Map<String, Object>> resp = controller.ingest(req, httpReq);

        assertEquals(HttpStatus.ACCEPTED, resp.getStatusCode());
        assertNotNull(resp.getBody());
        assertEquals("accepted", resp.getBody().get("status"));
        assertEquals(7L, resp.getBody().get("id"));
        assertEquals("pc-42", resp.getBody().get("pcId"));
        verify(metricsService).ingest(any(MetricsRequest.class), eq("pc-42"));
    }
}
