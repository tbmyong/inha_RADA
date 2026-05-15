-- V1 baseline schema for RADA main server (pc_monitor).
-- Faithful SQL expression of current JPA entities; no additional indexes
-- or constraints beyond what entities declare.

CREATE TABLE IF NOT EXISTS metrics_history (
    id            BIGSERIAL PRIMARY KEY,
    pc_id         VARCHAR(64)              NOT NULL,
    collected_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    cpu_usage     DOUBLE PRECISION,
    memory_usage  DOUBLE PRECISION,
    disk_usage    DOUBLE PRECISION,
    network_in    DOUBLE PRECISION,
    network_out   DOUBLE PRECISION,
    extra         JSONB
);

CREATE TABLE IF NOT EXISTS anomaly_history (
    id            BIGSERIAL PRIMARY KEY,
    pc_id         VARCHAR(64)              NOT NULL,
    detected_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    severity      VARCHAR(16)              NOT NULL,
    anomaly_type  VARCHAR(64),
    message       TEXT,
    scores        JSONB,
    alerts        JSONB
);

CREATE TABLE IF NOT EXISTS ai_judgment_history (
    id           BIGSERIAL PRIMARY KEY,
    pc_id        VARCHAR(64)              NOT NULL,
    judged_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    anomaly_id   BIGINT,
    model_name   VARCHAR(64),
    verdict      VARCHAR(32),
    confidence   DOUBLE PRECISION,
    details      JSONB
);

CREATE TABLE IF NOT EXISTS pc_info (
    pc_id          VARCHAR(64) PRIMARY KEY,
    hostname       VARCHAR(128),
    api_key        VARCHAR(128),
    is_active      BOOLEAN,
    registered_at  TIMESTAMP WITH TIME ZONE,
    last_seen_at   TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uk_pc_info_api_key UNIQUE (api_key)
);
