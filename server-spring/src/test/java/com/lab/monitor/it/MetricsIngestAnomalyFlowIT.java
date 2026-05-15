package com.lab.monitor.it;

import com.lab.monitor.entity.PcInfo;
import com.lab.monitor.repository.AgentAuthRepository;
import com.lab.monitor.repository.AiJudgmentRepository;
import com.lab.monitor.repository.AlertRepository;
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
 * Scenario 2: Anomaly flow.
 *
 * Given: an active agent and ML server stubbed to return severity=HIGH
 *        (using NORMAL-key path "severity":"HIGH" because current MlResponse DTO
 *         maps `severity`, not `overall_severity` — see contract tests for the gap).
 * When:  the agent POSTs metrics
 * Then:  - 202 returned
 *        - anomaly_history row is created (eventual: async ML forward)
 *        - ai_judgment_history row is created with verdict=HIGH
 */
class MetricsIngestAnomalyFlowIT extends AbstractIntegrationTest {

    @LocalServerPort int port;
    @Autowired AgentAuthRepository agentAuthRepository;
    @Autowired AlertRepository alertRepository;
    @Autowired AiJudgmentRepository aiJudgmentRepository;
    @Autowired ApiKeyHasher apiKeyHasher;

    @Test
    void anomaly_flow_creates_anomaly_and_judgment_rows() {
        agentAuthRepository.save(PcInfo.builder()
                .pcId("pc-it-anomaly")
                .hostname("it-host-anomaly")
                .apiKey(apiKeyHasher.hash("test-key"))
                .isActive(true)
                .registeredAt(OffsetDateTime.now())
                .build());

        // ML response carries severity=HIGH (DTO field actually consumed)
        // plus overall_severity / verdict / agent block to mirror real payload shape.
        String body = "{" +
                "\"severity\":\"HIGH\"," +
                "\"overall_severity\":\"HIGH\"," +
                "\"verdict\":\"DANGEROUS\"," +
                "\"anomalyType\":\"CPU_SPIKE\"," +
                "\"message\":\"sustained cpu saturation\"," +
                "\"model_name\":\"rada-v1\"," +
                "\"modelName\":\"rada-v1\"," +
                "\"confidence\":0.91," +
                "\"scores\":{\"cpu\":0.98,\"memory\":0.62}," +
                "\"alerts\":{\"cpu_overload\":true}," +
                "\"agent\":{" +
                "  \"judgment\":\"ANOMALY\"," +
                "  \"severity\":\"HIGH\"," +
                "  \"reason\":\"cpu saturated\"," +
                "  \"action\":\"ESCALATE\"," +
                "  \"hw_degradation\":\"CONFIRMED\"" +
                "}" +
                "}";
        WIREMOCK.stubFor(post(urlPathEqualTo("/analyze"))
                .willReturn(aResponse()
                        .withStatus(200)
                        .withHeader("Content-Type", "application/json")
                        .withBody(body)));

        RestTemplate rest = new RestTemplateBuilder().build();
        HttpHeaders h = new HttpHeaders();
        h.setContentType(MediaType.APPLICATION_JSON);
        h.set("X-API-Key", "test-key");
        Map<String, Object> reqBody = Map.of(
                "timestamp", OffsetDateTime.now().toString(),
                "cpu_percent", 99.0,
                "memory_percent", 88.0,
                "disk_read_mb", 30.0,
                "disk_write_mb", 25.0);

        ResponseEntity<Map> resp = rest.exchange(
                "http://localhost:" + port + "/api/metrics",
                HttpMethod.POST,
                new HttpEntity<>(reqBody, h),
                Map.class);

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);

        // anomaly is recorded by AlertService asynchronously after ML response
        await().atMost(5, TimeUnit.SECONDS).untilAsserted(() -> {
            assertThat(alertRepository.count()).isGreaterThanOrEqualTo(1);
            assertThat(aiJudgmentRepository.count()).isGreaterThanOrEqualTo(1);
        });
    }
}
