package com.lab.monitor.it;

import com.lab.monitor.entity.PcInfo;
import com.lab.monitor.repository.AgentAuthRepository;
import com.lab.monitor.repository.MetricsRepository;
import com.lab.monitor.security.ApiKeyHasher;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestTemplate;

import java.time.OffsetDateTime;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

/**
 * Scenario 3: API-key authentication failures.
 *
 * Cases:
 *   A) missing X-API-Key  -> 401, no DB writes
 *   B) unknown X-API-Key  -> 401, no DB writes
 *   C) inactive agent     -> 401, no DB writes
 */
class MetricsAuthFailureIT extends AbstractIntegrationTest {

    @LocalServerPort int port;
    @Autowired AgentAuthRepository agentAuthRepository;
    @Autowired MetricsRepository metricsRepository;
    @Autowired ApiKeyHasher apiKeyHasher;

    private final RestTemplate rest = new RestTemplateBuilder().build();

    private ResponseEntity<String> postWith(HttpHeaders h) {
        Map<String, Object> body = Map.of(
                "timestamp", OffsetDateTime.now().toString(),
                "cpu_percent", 1.0);
        h.setContentType(MediaType.APPLICATION_JSON);
        return rest.exchange(
                "http://localhost:" + port + "/api/metrics",
                HttpMethod.POST,
                new HttpEntity<>(body, h),
                String.class);
    }

    @Test
    void missing_api_key_returns_401_and_does_not_persist() {
        long before = metricsRepository.count();

        Throwable t = catchThrowable(() -> postWith(new HttpHeaders()));

        assertThat(t).isInstanceOf(HttpClientErrorException.Unauthorized.class);
        assertThat(metricsRepository.count()).isEqualTo(before);
    }

    @Test
    void unknown_api_key_returns_401_and_does_not_persist() {
        long before = metricsRepository.count();

        HttpHeaders h = new HttpHeaders();
        h.set("X-API-Key", "no-such-key");

        Throwable t = catchThrowable(() -> postWith(h));

        assertThat(t).isInstanceOf(HttpClientErrorException.Unauthorized.class);
        assertThat(metricsRepository.count()).isEqualTo(before);
    }

    @Test
    void inactive_agent_returns_401_and_does_not_persist() {
        agentAuthRepository.save(PcInfo.builder()
                .pcId("pc-inactive")
                .hostname("h-inactive")
                .apiKey(apiKeyHasher.hash("inactive-key"))
                .isActive(false)
                .registeredAt(OffsetDateTime.now())
                .build());

        long before = metricsRepository.count();
        HttpHeaders h = new HttpHeaders();
        h.set("X-API-Key", "inactive-key");

        Throwable t = catchThrowable(() -> postWith(h));

        assertThat(t).isInstanceOf(HttpClientErrorException.Unauthorized.class);
        assertThat(metricsRepository.count()).isEqualTo(before);
    }
}
