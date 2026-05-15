-- V6: Set default search_path for the rada role to include pc_monitor.
--
-- Why: Grafana dashboards (rada-main, rada-pc-detail) use schema-less
-- table references (e.g., `FROM metrics_history`). Without this, Postgres
-- only searches the `public` schema and Grafana panels return
-- `relation "metrics_history" does not exist`.
--
-- This is a role-level setting that applies to every new connection.
-- Pooled connections created BEFORE this migration ran need to be
-- recycled (e.g., restart Grafana once after first deploy).

ALTER ROLE rada SET search_path TO pc_monitor, public;
