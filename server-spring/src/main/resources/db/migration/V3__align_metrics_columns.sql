-- V3: align metrics_history columns with Agent payload key names.
-- Renames operational columns to match Agent v1.x snake_case keys,
-- drops the synthesized disk_usage column, and promotes the raw
-- disk read/write pair plus GPU operational fields out of `extra` jsonb
-- into dedicated DOUBLE PRECISION columns.

SET search_path TO ${flyway:defaultSchema};

ALTER TABLE metrics_history RENAME COLUMN cpu_usage    TO cpu_percent;
ALTER TABLE metrics_history RENAME COLUMN memory_usage TO mem_percent;
ALTER TABLE metrics_history RENAME COLUMN network_in   TO inbound_mb;
ALTER TABLE metrics_history RENAME COLUMN network_out  TO outbound_mb;

ALTER TABLE metrics_history DROP COLUMN disk_usage;

ALTER TABLE metrics_history
    ADD COLUMN disk_read_mb  DOUBLE PRECISION,
    ADD COLUMN disk_write_mb DOUBLE PRECISION,
    ADD COLUMN gpu_percent   DOUBLE PRECISION,
    ADD COLUMN vram_mb       DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_metrics_pc_collected
    ON metrics_history (pc_id, collected_at DESC);
