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
- Current migrations: **V1, V3, V4, V5, V6, V7, V8** (V2 의도적 skip).
  - `V1__baseline_schema.sql` — JPA entities baseline (`MetricsHistory`,
    `AnomalyHistory`, `AiJudgmentHistory`, `PcInfo`)
  - `V3__align_metrics_columns.sql` — metric column 정합화
  - `V4__hash_api_keys.sql` — API key SHA-256 해시 컬럼 전환
  - `V5__align_ai_judgment_and_pc_info.sql` — AI 판단/PC info 컬럼 정합
  - `V6__set_search_path.sql`, `V7__set_search_path_parametrized.sql` —
    application role 의 default search_path 설정 (placeholder 기반)
  - `V8__align_grafana_reader_search_path.sql` — grafana_reader role
    search_path 정렬 (없으면 멱등 skip)
- `spring.flyway.baseline-on-migrate=true` 활성 — Flyway 이력 테이블 없는
  기존 DB 는 version 0 으로 baseline 됨.
- 기본 schema 는 `pc_monitor` (override: `DB_SCHEMA` env).
- NCP managed Cloud DB for PostgreSQL 15.x 에서 V1~V8 모두 정상 적용 검증됨
  (`docs/fp_field_analysis_ncp.md` 참조).
