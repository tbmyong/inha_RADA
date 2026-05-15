package com.lab.monitor.controller;

import com.lab.monitor.dto.MetricsRequest;
import com.lab.monitor.security.ApiKeyAuthFilter;
import com.lab.monitor.service.MetricsService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/metrics")
@RequiredArgsConstructor
public class MetricsController {

    private final MetricsService metricsService;

    @PostMapping
    public ResponseEntity<Map<String, Object>> ingest(@Valid @RequestBody MetricsRequest req,
                                                      HttpServletRequest httpReq) {
        String pcId = (String) httpReq.getAttribute(ApiKeyAuthFilter.PC_ID_ATTR);
        var saved = metricsService.ingest(req, pcId);
        return ResponseEntity.accepted().body(Map.of(
                "status", "accepted",
                "id", saved.getId(),
                "pcId", pcId));
    }
}
