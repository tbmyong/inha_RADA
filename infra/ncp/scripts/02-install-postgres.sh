#!/usr/bin/env bash
# 02-install-postgres.sh
# PostgreSQL 15 설치 + 4GB RAM 환경에 맞춘 메모리 튜닝
# 주의: 본 스크립트는 CREATE TABLE / ALTER / 인덱스 생성을 절대 수행하지 않는다.
#       스키마는 백엔드 팀(JPA / Alembic)이 관리한다.

set -euo pipefail

PG_VERSION="15"
# NOTE: 기존 운영 DB가 'rada' 였다면 pg_dump → pc_monitor로 재적재(마이그레이션) 필요
DB_NAME="pc_monitor"
DB_OWNER="rada_app"
DB_OWNER_PASSWORD="${DB_OWNER_PASSWORD:-change_me_app}"

echo "[1/5] apt update & PostgreSQL ${PG_VERSION} 설치"
sudo apt-get update -y
sudo apt-get install -y "postgresql-${PG_VERSION}" "postgresql-client-${PG_VERSION}"

PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
PG_HBA="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"

echo "[2/5] postgresql.conf 튜닝 (4GB RAM 기준)"
sudo sed -i "s/^#\?listen_addresses.*/listen_addresses = 'localhost'/" "$PG_CONF"
sudo sed -i "s/^#\?shared_buffers.*/shared_buffers = 128MB/" "$PG_CONF"
sudo sed -i "s/^#\?work_mem.*/work_mem = 8MB/" "$PG_CONF"
sudo sed -i "s/^#\?maintenance_work_mem.*/maintenance_work_mem = 64MB/" "$PG_CONF"
sudo sed -i "s/^#\?effective_cache_size.*/effective_cache_size = 1GB/" "$PG_CONF"
sudo sed -i "s/^#\?max_connections.*/max_connections = 50/" "$PG_CONF"
sudo sed -i "s/^#\?timezone.*/timezone = 'UTC'/" "$PG_CONF"
sudo sed -i "s/^#\?log_timezone.*/log_timezone = 'UTC'/" "$PG_CONF"

echo "[3/5] pg_hba.conf — localhost 만 허용 (md5)"
# 기본 설정 그대로 두고 재확인만 (외부 host 라인은 추가하지 않는다)
grep -E "^host\s+all\s+all\s+127\.0\.0\.1/32\s+md5" "$PG_HBA" >/dev/null \
  || echo "host all all 127.0.0.1/32 md5" | sudo tee -a "$PG_HBA"

echo "[4/5] 서비스 재시작"
sudo systemctl enable --now postgresql
sudo systemctl restart postgresql

echo "[5/5] DB / 애플리케이션 OWNER 계정 생성 (DDL 은 수행하지 않음)"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_OWNER}') THEN
    CREATE ROLE ${DB_OWNER} LOGIN PASSWORD '${DB_OWNER_PASSWORD}';
  END IF;
END
\$\$;
SQL

# DATABASE 생성은 별도 세션으로. 위의 SELECT 'create database' ... \gexec 형태는
# fresh DB 에서 psql 이 literal string 'create database' 를 실행하려다 문법 오류로
# 종료되므로 제거. 아래의 format(...) 빌더가 올바른 CREATE DATABASE 문을 생성한다.
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
SELECT format('CREATE DATABASE %I OWNER %I', '${DB_NAME}', '${DB_OWNER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
SQL

echo "DONE. 스키마(테이블) 생성은 백엔드(JPA / Alembic) 측에서 수행한다."
