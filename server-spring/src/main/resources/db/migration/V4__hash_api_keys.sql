-- V4: hash pc_info.api_key with SHA-256(pepper || ':' || raw_key).
-- Idempotent: rows whose api_key is already a 64-char lowercase hex digest
-- are left untouched. Pepper is injected via Flyway placeholder
-- `${api_key_pepper}` (configured in spring.flyway.placeholders).
--
-- After this migration api_key is stored exclusively as the hex digest
-- (length 64) and the column is narrowed accordingly.

SET search_path TO ${flyway:defaultSchema};

CREATE EXTENSION IF NOT EXISTS pgcrypto;

UPDATE pc_info
SET api_key = encode(digest('${api_key_pepper}' || ':' || api_key, 'sha256'), 'hex')
WHERE length(api_key) <> 64 OR api_key !~ '^[0-9a-f]+$';

ALTER TABLE pc_info ALTER COLUMN api_key TYPE VARCHAR(64);
