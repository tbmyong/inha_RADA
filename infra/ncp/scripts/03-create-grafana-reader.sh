#!/usr/bin/env bash
# 03-create-grafana-reader.sh
# Grafana 전용 READ-ONLY 계정 생성.
# 절대 규칙:
#   - 이 스크립트는 GRANT SELECT 만 수행한다.
#   - CREATE TABLE / ALTER TABLE / CREATE INDEX 등 DDL 을 수행하지 않는다.
#   - 스키마는 백엔드 팀이 관리하며, 본 스크립트는 권한만 부여한다.
#
# 운영 정합성 노트 (2026-05):
#   - 02-install-postgres.sh 가 만드는 DB 는 ${DB_NAME:-pc_monitor} 다.
#     따라서 이 파일의 DB_NAME 기본값도 pc_monitor 로 맞춘다.
#   - Spring/Flyway 가 사용하는 schema 는 ${DB_SCHEMA:-pc_monitor} 다 (V3+).
#     Grafana datasource (postgres.yaml) 도 동일. SELECT/USAGE 권한과
#     기본 search_path 모두 이 스키마에 맞춰 부여한다.
#   - 기존엔 schema=public 으로 권한을 줘 운영 Grafana 가 schemaless
#     SQL ("FROM metrics_history" 등) 으로 안 잡히는 silent fail 가능성이
#     있었다. 본 fix 가 그것을 닫는다.

set -euo pipefail

DB_NAME="${DB_NAME:-pc_monitor}"
DB_SCHEMA="${DB_SCHEMA:-pc_monitor}"
READER_ROLE="grafana_reader"
READER_PASSWORD="${GRAFANA_READER_PASSWORD:-change_me_reader}"

echo "[1/3] grafana_reader 역할 생성/갱신"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${READER_ROLE}') THEN
    CREATE ROLE ${READER_ROLE} LOGIN PASSWORD '${READER_PASSWORD}';
  ELSE
    ALTER ROLE ${READER_ROLE} WITH LOGIN PASSWORD '${READER_PASSWORD}';
  END IF;
END
\$\$;

-- search_path 를 운영 schema 우선으로 설정. dashboard SQL 이
-- "FROM metrics_history" 처럼 schema 를 생략해도 정상 resolve.
ALTER ROLE ${READER_ROLE} SET search_path TO ${DB_SCHEMA}, public;
SQL

echo "[2/3] ${DB_NAME}.${DB_SCHEMA} 에 SELECT 권한 부여 (DDL 권한 없음)"
sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" <<SQL
-- 접속/스키마 사용
GRANT CONNECT ON DATABASE ${DB_NAME}    TO ${READER_ROLE};
GRANT USAGE   ON SCHEMA   ${DB_SCHEMA}  TO ${READER_ROLE};

-- 현재 존재하는 모든 테이블/시퀀스에 SELECT 만 부여
GRANT SELECT ON ALL TABLES    IN SCHEMA ${DB_SCHEMA} TO ${READER_ROLE};
GRANT SELECT ON ALL SEQUENCES IN SCHEMA ${DB_SCHEMA} TO ${READER_ROLE};

-- 향후 백엔드가 새로 만드는 테이블에도 자동으로 SELECT 가 부여되도록 default privileges 설정
ALTER DEFAULT PRIVILEGES IN SCHEMA ${DB_SCHEMA} GRANT SELECT ON TABLES    TO ${READER_ROLE};
ALTER DEFAULT PRIVILEGES IN SCHEMA ${DB_SCHEMA} GRANT SELECT ON SEQUENCES TO ${READER_ROLE};
SQL

echo "[3/3] public 스키마 USAGE 도 별도 부여 (fallback, 예: extension 함수)"
sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" <<SQL
GRANT USAGE ON SCHEMA public TO ${READER_ROLE};
SQL

echo "DONE. grafana_reader 는 ${DB_SCHEMA}.* 에 SELECT 만 가능하다 (CREATE / INSERT / UPDATE / DELETE 불가)."
