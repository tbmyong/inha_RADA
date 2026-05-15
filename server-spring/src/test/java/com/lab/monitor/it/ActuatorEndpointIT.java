package com.lab.monitor.it;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

/**
 * Verifies Actuator exposure policy:
 *   - {@code /actuator/health}  -> 200 UP, no nested components/details
 *   - {@code /actuator/metrics} -> 404 (NOT exposed in management.endpoints.web.exposure)
 *
 * Lives under {@link AbstractIntegrationTest} because the policy is enforced
 * by the full Spring context + Security filter chain; a slice test would
 * not exercise the {@code management.endpoint.health.show-details} property.
 */
class ActuatorEndpointIT extends AbstractIntegrationTest {

    @LocalServerPort int port;

    private final RestTemplate rest = new RestTemplateBuilder().build();

    @Test
    void health_returns_200_and_does_not_leak_components() {
        ResponseEntity<String> resp = rest.getForEntity(
                "http://localhost:" + port + "/actuator/health", String.class);

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        String body = resp.getBody();
        assertThat(body).isNotNull();
        // show-details: never -> no "components" / "details" keys leaked
        assertThat(body).doesNotContain("components");
        assertThat(body).doesNotContain("details");
        // status is the only meaningful field surfaced
        assertThat(body).contains("\"status\"");
    }

    @Test
    void metrics_endpoint_is_not_exposed() {
        Throwable t = catchThrowable(() -> rest.getForEntity(
                "http://localhost:" + port + "/actuator/metrics", String.class));

        assertThat(t).isInstanceOf(HttpClientErrorException.NotFound.class);
    }
}
