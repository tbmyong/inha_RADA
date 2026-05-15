#!/usr/bin/env bash
# 03-create-grafana-reader.sh
# Grafana 전용 READ-ONLY 계정 생성.
# 절대 규칙:
#   - 이 스크립트는 GRANT SELECT 만 수행한다.
#   - CREATE TABLE / ALTER TABLE / CREATE INDEX 등 DDL 을 수행하지 않는다.
#   - 스키마는 백엔드 팀이 관리하며, 본 스크립트는 권한만 부여한다.

set -euo pipefail

DB_NAME="${DB_NAME:-rada}"
READER_ROLE="grafana_reader"
READER_PASSWORD="${GRAFANA_READER_PASSWORD:-change_me_reader}"

echo "[1/2] grafana_reader 역할 생성/갱신"
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
SQL

echo "[2/2] ${DB_NAME} 에 SELECT 권한 부여 (DDL 권한 없음)"
sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" <<SQL
-- 접속/스키마 사용
GRANT CONNECT ON DATABASE ${DB_NAME} TO ${READER_ROLE};
GRANT USAGE   ON SCHEMA public      TO ${READER_ROLE};

-- 현재 존재하는 모든 테이블/시퀀스에 SELECT 만 부여
GRANT SELECT ON ALL TABLES    IN SCHEMA public TO ${READER_ROLE};
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO ${READER_ROLE};

-- 향후 백엔드가 새로 만드는 테이블에도 자동으로 SELECT 가 부여되도록 default privileges 설정
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES    TO ${READER_ROLE};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO ${READER_ROLE};
SQL

echo "DONE. grafana_reader 는 SELECT 만 가능하다 (CREATE / INSERT / UPDATE / DELETE 불가)."
