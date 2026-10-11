CREATE OR REPLACE VIEW analytics_events AS
SELECT event_id, camera_id, occurred_at, object_type, confidence, description,
       risk_level, alert_status, model_version
FROM events
WHERE description IS NOT NULL AND btrim(description) <> '';

CREATE TABLE IF NOT EXISTS query_audit_log (
    id BIGSERIAL PRIMARY KEY,
    request_hash VARCHAR(64) NOT NULL,
    route VARCHAR(16) NOT NULL,
    operation VARCHAR(32),
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome VARCHAR(32) NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    result_count INTEGER NOT NULL DEFAULT 0,
    error_code VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS query_audit_log_created_at_idx ON query_audit_log (created_at DESC);
