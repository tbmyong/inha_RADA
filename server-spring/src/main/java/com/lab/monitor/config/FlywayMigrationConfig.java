package com.lab.monitor.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.flyway.FlywayMigrationStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Run {@code flyway repair} before {@code migrate} on startup — gated.
 *
 * <p>Why: when a previously-applied migration file is modified (e.g. V6 was
 * rewritten to use Flyway placeholders after originally being hard-coded),
 * Flyway's checksum validation rejects the new file with
 * {@code MigrationChecksumMismatch}. {@code repair()} refreshes the
 * checksum column in {@code flyway_schema_history} so the next
 * {@code migrate()} call succeeds.
 *
 * <p>OPERATIONAL RISK: leaving {@code repair()} always-on means an unintended
 * checksum drift in production (someone modifies a historical migration)
 * gets silently auto-healed instead of stopping the deploy. That defeats
 * the integrity check Flyway is supposed to provide.
 *
 * <p>This bean is therefore gated by {@code rada.flyway.auto-repair=true}.
 * The Docker dev profile ({@code application-docker.yml}) sets it to
 * {@code true} so local rebuilds tolerate the historical V6 rewrite.
 * The default ({@code application.yml}, used by NCP systemd) leaves it
 * {@code false} — production failures must be investigated explicitly.
 *
 * <p>Once all deployed environments (dev + NCP production) have re-checksummed
 * V6 once, this whole class can be removed.
 */
@Slf4j
@Configuration
@ConditionalOnProperty(name = "rada.flyway.auto-repair", havingValue = "true")
public class FlywayMigrationConfig {

    @Bean
    public FlywayMigrationStrategy repairThenMigrate() {
        return flyway -> {
            try {
                log.info("Flyway: rada.flyway.auto-repair=true -> repair() before migrate()");
                flyway.repair();
            } catch (Exception e) {
                // repair is best-effort. If it fails (e.g. fresh DB), continue.
                log.warn("Flyway repair() skipped or failed: {}", e.getMessage());
            }
            flyway.migrate();
        };
    }
}
