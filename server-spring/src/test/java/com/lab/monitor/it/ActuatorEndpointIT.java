package com.lab.monitor.it;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

/**
 * Verifies Actuator exposure policy after F1 split:
 *   - Actuator endpoints live on a SEPARATE management port (8081 in prod;
 *     a random port in tests via {@link LocalManagementPort}).
 *   - {@code /actuator/health}     -> 200 UP, no nested components
 *   - {@code /actuator/metrics}    -> 200 (exposed for ops; not on app port)
 *   - {@code /actuator/prometheus} -> 200 (Grafana scrape target)
 *   - Hitting {@code /actuator/*} on the app port -> 404 (port split intact)
 *
 * Lives under {@link AbstractIntegrationTest} because the policy is enforced
 * by the full Spring context + Security filter chain; a slice test would
 * not exercise the {@code management.endpoint.health.show-details} property.
 */
class ActuatorEndpointIT extends AbstractIntegrationTest {

    @LocalServerPort int appPort;
    @LocalManagementPort int mgmtPort;

    private final RestTemplate rest = new RestTemplateBuilder().build();

    @Test
    void health_returns_200_and_does_not_leak_components() {
        ResponseEntity<String> resp = rest.getForEntity(
                "http://localhost:" + mgmtPort + "/actuator/health", String.class);

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        String body = resp.getBody();
        assertThat(body).isNotNull();
        // show-components: never -> no "components" key leaked even when
        // show-details would otherwise allow it.
        assertThat(body).doesNotContain("components");
        // status is the only meaningful field surfaced
        assertThat(body).contains("\"status\"");
    }

    @Test
    void metrics_endpoint_is_exposed_on_management_port() {
        ResponseEntity<String> resp = rest.getForEntity(
                "http://localhost:" + mgmtPort + "/actuator/metrics", String.class);

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(resp.getBody()).contains("names");
    }

    @Test
    void prometheus_endpoint_is_exposed_on_management_port() {
        ResponseEntity<String> resp = rest.getForEntity(
                "http://localhost:" + mgmtPort + "/actuator/prometheus", String.class);

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        // Micrometer Prometheus exposition format begins with "# HELP" lines.
        assertThat(resp.getBody()).contains("# HELP");
    }

    @Test
    void actuator_is_not_reachable_on_application_port() {
        Throwable t = catchThrowable(() -> rest.getForEntity(
                "http://localhost:" + appPort + "/actuator/health", String.class));

        assertThat(t).isInstanceOf(HttpClientErrorException.NotFound.class);
    }
}
