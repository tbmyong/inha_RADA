# RADA Main Server (Spring Boot)

## Prerequisites
- JDK 17
- Docker daemon running (required for Testcontainers-backed integration tests)

## Build & Test
- Unix/macOS: `./gradlew test`
- Windows:   `gradlew.bat test`

## Gradle Wrapper jar (manual step)

This repository ships `gradlew`, `gradlew.bat`, and
`gradle/wrapper/gradle-wrapper.properties`, but **`gradle/wrapper/gradle-wrapper.jar`
is not committed** because the offline build environment used to scaffold this
project could not download it from either GitHub or Maven Central.

Generate the jar once locally with a system Gradle 8.5 install:

```
gradle wrapper --gradle-version 8.5
```

Or download it directly:

- GitHub: <https://raw.githubusercontent.com/gradle/gradle/v8.5.0/gradle/wrapper/gradle-wrapper.jar>
- Place at: `gradle/wrapper/gradle-wrapper.jar`

After the jar is in place, `./gradlew` / `gradlew.bat` work as normal.

## Database Migrations (Flyway)

- Migration scripts live under `src/main/resources/db/migration`.
- `V1__baseline_schema.sql` is the baseline expression of the current JPA
  entities (`MetricsHistory`, `AnomalyHistory`, `AiJudgmentHistory`, `PcInfo`).
- `spring.flyway.baseline-on-migrate=true` is enabled so existing PostgreSQL
  databases without a Flyway history table are baselined at version 0.
- The default schema is `pc_monitor` (override via `DB_SCHEMA`).
