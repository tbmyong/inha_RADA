-- ============================================================================
-- RADA demo seed — DEV ONLY.
-- Populates 40 PCs with realistic metrics, anomalies, AI judgments.
-- Idempotent: deletes prior demo rows first.
-- Do NOT run on production. Run via infra/seed/seed_demo.ps1 or:
--   docker compose exec -T postgres psql -U rada -d pc_monitor < demo_data.sql
-- ============================================================================

SET search_path TO pc_monitor;

BEGIN;

-- Wipe previous demo data (keeps schema, keeps non-demo rows by pc_id prefix).
DELETE FROM ai_judgment_history WHERE pc_id LIKE 'PC-%';
DELETE FROM anomaly_history     WHERE pc_id LIKE 'PC-%';
DELETE FROM metrics_history     WHERE pc_id LIKE 'PC-%';
DELETE FROM pc_info             WHERE pc_id LIKE 'PC-%';

-- ---------------------------------------------------------------- pc_info ---
INSERT INTO pc_info (pc_id, hostname, api_key, is_active, registered_at, last_seen_at, location, gpu_available)
SELECT
  format('PC-%s', lpad(g::text, 2, '0')),
  format('lab01-pc-%s', lpad(g::text, 2, '0')),
  md5('demo-key-' || g::text),
  true,
  NOW() - INTERVAL '30 days',
  NOW() - (random() * INTERVAL '30 seconds'),
  'LAB-01',
  true
FROM generate_series(1, 40) AS g;

-- ---------------------------------------------------------- pc-smoke (dev) ---
-- Smoke-test PC consumed by tools/anomaly_trigger.py.
-- The api_key column stores SHA-256(pepper + ":" + raw_key) lowercase hex.
-- Raw key is 'smoke-key', pepper is the dev default 'dev_pepper_change_me'.
-- If you rotate the pepper in .env this hash must be regenerated.
INSERT INTO pc_info (pc_id, hostname, api_key, is_active, registered_at, last_seen_at, location, gpu_available)
VALUES (
  'pc-smoke', 'smoke-host',
  'a94937b42b839452c176d00200ffd938536db499ad2ce273dfd1e2c1924ed0b3',
  true, NOW() - INTERVAL '30 days', NOW(), 'LAB-01', true
)
ON CONFLICT (pc_id) DO UPDATE
SET api_key = EXCLUDED.api_key,
    is_active = true,
    last_seen_at = NOW();

-- --------------------------------------------------------- metrics_history ---
-- 1 row / minute / PC for the last 60 minutes. CPU profile depends on PC index:
--   PC-07, PC-13 : mining-suspect (CPU 80-95, GPU 85-99)
--   PC-04, PC-21, PC-29, PC-33 : needs-review (CPU 55-75, GPU 40-70)
--   everyone else: normal (CPU 8-30, GPU 5-25)
INSERT INTO metrics_history
  (pc_id, collected_at, cpu_percent, mem_percent, gpu_percent, vram_mb,
   disk_read_mb, disk_write_mb, inbound_mb, outbound_mb, extra)
SELECT
  pc.pc_id,
  NOW() - (m || ' minutes')::interval AS collected_at,
  CASE
    WHEN pc.pc_id IN ('PC-07','PC-13')                                THEN 80 + random() * 15
    WHEN pc.pc_id IN ('PC-04','PC-21','PC-29','PC-33')                THEN 55 + random() * 20
    ELSE                                                                   8 + random() * 22
  END AS cpu_percent,
  20 + random() * 40 AS mem_percent,
  CASE
    WHEN pc.pc_id IN ('PC-07','PC-13')                                THEN 85 + random() * 14
    WHEN pc.pc_id IN ('PC-04','PC-21','PC-29','PC-33')                THEN 40 + random() * 30
    ELSE                                                                   5 + random() * 20
  END AS gpu_percent,
  CASE
    WHEN pc.pc_id IN ('PC-07','PC-13')                                THEN 7000 + random() * 1500
    WHEN pc.pc_id IN ('PC-04','PC-21','PC-29','PC-33')                THEN 3500 + random() * 1500
    ELSE                                                                   800 + random() * 1500
  END AS vram_mb,
  random() * 5  AS disk_read_mb,
  random() * 3  AS disk_write_mb,
  random() * 2  AS inbound_mb,
  random() * 1  AS outbound_mb,
  '{}'::jsonb
FROM pc_info pc
CROSS JOIN generate_series(0, 59) AS m
WHERE pc.pc_id LIKE 'PC-%';

-- --------------------------------------------------------- anomaly_history ---
-- 2 HIGH (MINING_SUSPECTED) + 4 MEDIUM (NEEDS_REVIEW)
INSERT INTO anomaly_history (pc_id, detected_at, severity, anomaly_type, message, scores, alerts)
VALUES
  ('PC-07', NOW() - INTERVAL '3 minutes',  'HIGH',   'MINING_SUSPECTED',
   'Sustained GPU utilization with low entropy workload',
   '{"score_breakdown":{"final":42.5,"gpu":18.0,"cpu":14.0,"pattern":10.5}}'::jsonb,
   '[{"signal":"gpu_sustained_high"},{"signal":"low_io"}]'::jsonb),
  ('PC-13', NOW() - INTERVAL '7 minutes',  'HIGH',   'MINING_SUSPECTED',
   'Tensor core idle while SM > 90%',
   '{"score_breakdown":{"final":38.2,"gpu":17.0,"cpu":12.0,"pattern":9.2}}'::jsonb,
   '[{"signal":"tensor_core_idle"}]'::jsonb),
  ('PC-04', NOW() - INTERVAL '11 minutes', 'MEDIUM', 'NEEDS_REVIEW',
   'Elevated CPU baseline drift',
   '{"score_breakdown":{"final":24.0,"cpu":12.0,"baseline":12.0}}'::jsonb,
   '[{"signal":"cpu_baseline_drift"}]'::jsonb),
  ('PC-21', NOW() - INTERVAL '17 minutes', 'MEDIUM', 'NEEDS_REVIEW',
   'GPU utilization above class slot threshold',
   '{"score_breakdown":{"final":21.5,"gpu":10.5,"threshold":11.0}}'::jsonb,
   '[{"signal":"gpu_over_threshold"}]'::jsonb),
  ('PC-29', NOW() - INTERVAL '25 minutes', 'MEDIUM', 'NEEDS_REVIEW',
   'Memory pressure rising trend',
   '{"score_breakdown":{"final":19.0,"mem":11.0,"trend":8.0}}'::jsonb,
   '[{"signal":"mem_trend_up"}]'::jsonb),
  ('PC-33', NOW() - INTERVAL '34 minutes', 'MEDIUM', 'NEEDS_REVIEW',
   'Disk I/O burst pattern',
   '{"score_breakdown":{"final":18.2,"disk":10.0,"pattern":8.2}}'::jsonb,
   '[{"signal":"disk_burst"}]'::jsonb);

-- ----------------------------------------------------- ai_judgment_history ---
-- 25 judgments total spread across the last hour.
-- 20 Normal (80%) / 2 Mining (8%) / 2 Heavy Load (8%) / 1 HW Error (4%) ~ matches mockup.
INSERT INTO ai_judgment_history
  (pc_id, judged_at, anomaly_id, model_name, verdict, confidence, details,
   judgment, severity, reason, action, is_mock)
SELECT
  format('PC-%s', lpad(((g * 3) % 40 + 1)::text, 2, '0')),
  NOW() - (g || ' minutes')::interval,
  NULL, 'mock-agent',
  CASE
    WHEN g IN (2, 22)        THEN 'mining_suspected'
    WHEN g IN (8, 30)        THEN 'heavy_load'
    WHEN g IN (15)           THEN 'hw_error'
    ELSE                          'normal'
  END,
  0.7 + random() * 0.25,
  '{}'::jsonb,
  CASE
    WHEN g IN (2, 22)        THEN 'MINING'
    WHEN g IN (8, 30)        THEN 'HEAVY_LOAD'
    WHEN g IN (15)           THEN 'HW_ERROR'
    ELSE                          'NORMAL'
  END,
  CASE
    WHEN g IN (2, 22)        THEN 'HIGH'
    WHEN g IN (8, 30)        THEN 'MEDIUM'
    WHEN g IN (15)           THEN 'LOW'
    ELSE                          'NORMAL'
  END,
  'auto-seeded demo judgment',
  'observe',
  true
FROM generate_series(1, 25) AS g;

COMMIT;

-- Quick sanity counts.
SELECT 'pc_info'             AS tbl, COUNT(*) FROM pc_info             WHERE pc_id LIKE 'PC-%'
UNION ALL SELECT 'metrics',          COUNT(*) FROM metrics_history     WHERE pc_id LIKE 'PC-%'
UNION ALL SELECT 'anomaly',          COUNT(*) FROM anomaly_history     WHERE pc_id LIKE 'PC-%'
UNION ALL SELECT 'judgment',         COUNT(*) FROM ai_judgment_history WHERE pc_id LIKE 'PC-%';
