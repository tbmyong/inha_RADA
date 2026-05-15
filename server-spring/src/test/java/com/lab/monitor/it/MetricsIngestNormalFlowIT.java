package com.lab.monitor.it;

import com.lab.monitor.entity.PcInfo;
import com.lab.monitor.repository.AgentAuthRepository;
import com.lab.monitor.repository.AlertRepository;
import com.lab.monitor.repository.MetricsRepository;
import com.lab.monitor.security.ApiKeyHasher;
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
 * Scenario 1: Normal-flow ingest.
 *
 * Given: an active agent registered with API key "test-key"
 *        and the ML server stubbed to return overall_severity=NORMAL
 * When:  the agent POSTs metrics to /api/metrics
 * Then:  - HTTP 202 ACCEPTED is returned
 *        - metrics_history row is persisted (count > 0)
 *        - anomaly_history remains empty (NORMAL is filtered upstream in AlertService)
 */
class MetricsIngestNormalFlowIT extends AbstractIntegrationTest {

    @LocalServerPort int port;
    @Autowired AgentAuthRepository agentAuthRepository;
    @Autowired MetricsRepository metricsRepository;
    @Autowired AlertRepository alertRepository;
    @Autowired ApiKeyHasher apiKeyHasher;

    @Test
    void normal_flow_persists_metrics_and_skips_anomaly() {
        // arrange: agent
        PcInfo pc = PcInfo.builder()
                .pcId("pc-it-normal")
                .hostname("it-host-normal")
                .apiKey(apiKeyHasher.hash("test-key"))
                .isActive(true)
                .registeredAt(OffsetDateTime.now())
                .build();
        agentAuthRepository.save(pc);

        // arrange: ML stub -> NORMAL
        WIREMOCK.stubFor(post(urlPathEqualTo("/analyze"))
                .willReturn(aResponse()
                        .withStatus(200)
                        .withHeader("Content-Type", "application/json")
                        .withBody("{\"severity\":\"NORMAL\",\"overall_severity\":\"NORMAL\"," +
                                "\"model_name\":\"rada-v1\",\"confidence\":0.99," +
                                "\"scores\":{\"cpu\":0.05}}")));

        // act
        RestTemplate rest = new RestTemplateBuilder()
                .setConnectTimeout(java.time.Duration.ofSeconds(2))
                .setReadTimeout(java.time.Duration.ofSeconds(5))
                .build();
        HttpHeaders h = new HttpHeaders();
        h.setContentType(MediaType.APPLICATION_JSON);
        h.set("X-API-Key", "test-key");
        Map<String, Object> body = Map.of(
                "timestamp", OffsetDateTime.now().toString(),
                "cpu_percent", 12.3,
                "memory_percent", 35.0);
        ResponseEntity<Map> resp = rest.exchange(
                "http://localhost:" + port + "/api/metrics",
                HttpMethod.POST,
                new HttpEntity<>(body, h),
                Map.class);

        // assert response
        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        assertThat(resp.getBody()).containsEntry("status", "accepted");
        assertThat(resp.getBody()).containsEntry("pcId", "pc-it-normal");

        // assert persistence (sync part already done before 202)
        assertThat(metricsRepository.count()).isGreaterThanOrEqualTo(1);

        // assert: NORMAL severity must NOT create anomaly row (eventual; async)
        await().atMost(3, TimeUnit.SECONDS).untilAsserted(() ->
                assertThat(alertRepository.count()).isEqualTo(0));
    }
}
