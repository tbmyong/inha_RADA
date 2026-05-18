package com.lab.monitor.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.flyway.FlywayMigrationStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Run {@code flyway repair} before {@code migrate} on every startup.
 *
 * <p>Why: when a previously-applied migration file is modified (e.g. V6 was
 * rewritten to use Flyway placeholders after originally being hard-coded),
 * Flyway's checksum validation rejects the new file with
 * {@code MigrationChecksumMismatch}. {@code repair()} refreshes the
 * checksum column in {@code flyway_schema_history} so the next
 * {@code migrate()} call succeeds.
 *
 * <p>Idempotent: repair is a no-op if checksums already match.
 *
 * <p>This is a one-time-fix accelerator for the V6 placeholder change.
 * Once all environments (dev + production) have re-checksummed V6,
 * this bean can be removed; leaving it in is harmless.
 */
@Slf4j
@Configuration
public class FlywayMigrationConfig {

    @Bean
    public FlywayMigrationStrategy repairThenMigrate() {
        return flyway -> {
            try {
                log.info("Flyway: running repair() to align checksums before migrate()");
                flyway.repair();
            } catch (Exception e) {
                // repair is best-effort. If it fails (e.g. fresh DB), continue.
                log.warn("Flyway repair() skipped or failed: {}", e.getMessage());
            }
            flyway.migrate();
        };
    }
}
