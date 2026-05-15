package com.lab.monitor.it;

import com.github.tomakehurst.wiremock.WireMockServer;
import com.github.tomakehurst.wiremock.core.WireMockConfiguration;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

/**
 * Singleton-container base for integration tests.
 *
 * Bootstraps:
 *   - PostgreSQL 15 Testcontainer (single instance reused across tests via static init)
 *   - WireMock HTTP server (single instance reused; reset between tests)
 *
 * Subclasses run with full Spring context (@SpringBootTest) and test profile.
 *
 * NOTE: requires a running Docker daemon to execute `gradle test`.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@Testcontainers
public abstract class AbstractIntegrationTest {

    protected static final PostgreSQLContainer<?> POSTGRES;
    protected static final WireMockServer WIREMOCK;

    static {
        POSTGRES = new PostgreSQLContainer<>(DockerImageName.parse("postgres:15-alpine"))
                .withDatabaseName("pc_monitor")
                .withUsername("test")
                .withPassword("test")
                .withReuse(true);
        POSTGRES.start();

        WIREMOCK = new WireMockServer(WireMockConfiguration.options().dynamicPort());
        WIREMOCK.start();
    }

    @BeforeAll
    static void ensureStarted() {
        if (!POSTGRES.isRunning()) {
            POSTGRES.start();
        }
        if (!WIREMOCK.isRunning()) {
            WIREMOCK.start();
        }
    }

    @AfterAll
    static void resetWireMockAll() {
        WIREMOCK.resetAll();
    }

    @BeforeEach
    void resetWireMockEach() {
        WIREMOCK.resetAll();
    }

    @DynamicPropertySource
    static void registerProps(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");

        // ddl-auto=validate by default; tests intentionally do not mutate schema.
        // Schema baseline is expected to be applied externally before integration test run.
        registry.add("spring.jpa.hibernate.ddl-auto", () -> "validate");

        // ML server URL points at WireMock for both runtime and plan-spec keys.
        registry.add("ml.server.base-url", WIREMOCK::baseUrl);
        registry.add("app.ml.base-url", WIREMOCK::baseUrl);
        registry.add("WIREMOCK_URL", WIREMOCK::baseUrl);
    }
}
