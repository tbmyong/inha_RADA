-- V8: Idempotent search_path alignment for the grafana_reader role.
--
-- Why: the operational fix lives in `infra/ncp/scripts/03-create-grafana-reader.sh`
-- (which runs `ALTER ROLE grafana_reader SET search_path TO ${DB_SCHEMA}, public`).
-- This migration is a defensive safety net: if a deployment runs the
-- application before the operator runs the bootstrap script, the role may
-- have been pre-created without the schema preference, leaving Grafana
-- dashboards (which use schema-less SQL) silently empty.
--
-- This script only fires when the role already exists. It does NOT
-- create the role (that is the operator's responsibility). The ALTER ROLE
-- is idempotent — applying it twice is safe.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_reader') THEN
        EXECUTE format(
            'ALTER ROLE grafana_reader SET search_path TO %I, public',
            '${db_schema}'
        );
    END IF;
END
$$;
