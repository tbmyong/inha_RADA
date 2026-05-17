-- V7: Parametrized search_path setting for the application DB role.
--
-- Why: V6 hardcoded the role name "rada", which broke deployments where
-- POSTGRES_USER / DB_SCHEMA were customized. V7 uses Flyway placeholders
-- (${db_user}, ${db_schema}) populated from environment variables so the
-- same migration works in any environment.
--
-- V6 is left in place (immutable history) but is functionally superseded
-- by this migration. On environments where db_user == 'rada' the ALTER is
-- idempotent and harmless.

ALTER ROLE "${db_user}" SET search_path TO ${db_schema}, public;
