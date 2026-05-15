package com.lab.monitor.it;

import com.lab.monitor.entity.PcInfo;
import com.lab.monitor.repository.AgentAuthRepository;
import com.lab.monitor.repository.AlertRepository;
import com.lab.monitor.repository.MetricsRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.post;
import static com.github.tomakehurst.wiremock.client.WireMock.urlPathEqualTo;
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

/**
 * Scenario 4: ML-server failure isolation.
 *
 * Given: ML server stub returns HTTP 500 (and a separate case: connection-reset / fault).
 * When:  agent POSTs metrics
 * Then:  - 202 ACCEPTED still returned (ingest path is sync; ML forward is async/best-effort)
 *        - metrics_history row exists
 *        - anomaly_history remains empty (no judgment can be derived)
 *        - no exception is propagated to caller
 */
class MlServerFailureIsolationIT extends AbstractIntegrationTest {

    @LocalServerPort int port;
    @Autowired AgentAuthRepository agentAuthRepository;
    @Autowired MetricsRepository metricsRepository;
    @Autowired AlertRepository alertRepository;

    @Test
    void ml_5xx_does_not_break_ingest() {
        agentAuthRepository.save(PcInfo.builder()
                .pcId("pc-it-mlfail")
                .hostname("h-mlfail")
                .apiKey("test-key")
                .isActive(true)
                .registeredAt(OffsetDateTime.now())
                .build());

        WIREMOCK.stubFor(post(urlPathEqualTo("/analyze"))
                .willReturn(aResponse()
                        .withStatus(500)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"error\":\"boom\"}")));

        long beforeMetrics = metricsRepository.count();
        long beforeAnomaly = alertRepository.count();

        RestTemplate rest = new RestTemplateBuilder().build();
        HttpHeaders h = new HttpHeaders();
        h.setContentType(MediaType.APPLICATION_JSON);
        h.set("X-API-Key", "test-key");
        Map<String, Object> body = Map.of(
                "timestamp", OffsetDateTime.now().toString(),
                "cpu_percent", 50.0);

        ResponseEntity<Map> resp = rest.exchange(
                "http://localhost:" + port + "/api/metrics",
                HttpMethod.POST,
                new HttpEntity<>(body, h),
                Map.class);

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        assertThat(metricsRepository.count()).isEqualTo(beforeMetrics + 1);

        // Give async ML forward time to fail; anomaly count must stay flat.
        await().atMost(4, TimeUnit.SECONDS).pollDelay(1, TimeUnit.SECONDS).untilAsserted(() ->
                assertThat(alertRepository.count()).isEqualTo(beforeAnomaly));
    }
}
