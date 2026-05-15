-- V5: align ai_judgment_history with spec (judgment/severity/reason/action/is_mock),
-- add missing pc_info columns (location, gpu_available), add FK constraints
-- (NOT VALID, no historical scan), and add anomaly_history query indexes.
-- All operations are idempotent / additive; existing rows preserve their data.

SET search_path TO ${flyway:defaultSchema};

-- ai_judgment_history spec columns -------------------------------------------
ALTER TABLE ai_judgment_history
    ADD COLUMN IF NOT EXISTS judgment VARCHAR(64),
    ADD COLUMN IF NOT EXISTS severity VARCHAR(16),
    ADD COLUMN IF NOT EXISTS reason   TEXT,
    ADD COLUMN IF NOT EXISTS action   TEXT,
    ADD COLUMN IF NOT EXISTS is_mock  BOOLEAN;

-- Backfill from existing details jsonb (idempotent via COALESCE)
UPDATE ai_judgment_history
SET judgment = COALESCE(judgment, details->>'judgment'),
    severity = COALESCE(severity, details->>'agent_severity', details->>'severity'),
    reason   = COALESCE(reason,   details->>'reason'),
    action   = COALESCE(action,   details->>'action'),
    is_mock  = COALESCE(is_mock,
                        CASE
                            WHEN details->>'is_mock' = 'true'  THEN true
                            WHEN details->>'is_mock' = 'false' THEN false
                            ELSE NULL
                        END)
WHERE details IS NOT NULL;

-- pc_info missing columns ----------------------------------------------------
ALTER TABLE pc_info
    ADD COLUMN IF NOT EXISTS location      VARCHAR(128),
    ADD COLUMN IF NOT EXISTS gpu_available BOOLEAN;

-- FK constraints (NOT VALID — applies to new rows, skips historical scan) ----
ALTER TABLE metrics_history
    ADD CONSTRAINT fk_metrics_pc
    FOREIGN KEY (pc_id) REFERENCES pc_info(pc_id) NOT VALID;

ALTER TABLE anomaly_history
    ADD CONSTRAINT fk_anomaly_pc
    FOREIGN KEY (pc_id) REFERENCES pc_info(pc_id) NOT VALID;

ALTER TABLE ai_judgment_history
    ADD CONSTRAINT fk_aij_anomaly
    FOREIGN KEY (anomaly_id) REFERENCES anomaly_history(id) NOT VALID;

-- anomaly_history query indexes ----------------------------------------------
CREATE INDEX IF NOT EXISTS idx_anomaly_pc_detected
    ON anomaly_history (pc_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomaly_severity_detected
    ON anomaly_history (severity, detected_at DESC);
