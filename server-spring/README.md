# RADA Main Server (Spring Boot)

## Prerequisites
- JDK 17
- Docker daemon running (required for Testcontainers-backed integration tests)

## Build & Test
- Unix/macOS: `./gradlew test`
- Windows:   `gradlew.bat test`

## Gradle Wrapper

`gradle/wrapper/gradle-wrapper.jar` is committed in this repo, so
`./gradlew` / `gradlew.bat` work right after `git clone` without any
manual download. No extra step needed.

## Database Migrations (Flyway)

- Migration scripts live under `src/main/resources/db/migration`.
- `V1__baseline_schema.sql` is the baseline expression of the current JPA
  entities (`MetricsHistory`, `AnomalyHistory`, `AiJudgmentHistory`, `PcInfo`).
- `spring.flyway.baseline-on-migrate=true` is enabled so existing PostgreSQL
  databases without a Flyway history table are baselined at version 0.
- The default schema is `pc_monitor` (override via `DB_SCHEMA`).
