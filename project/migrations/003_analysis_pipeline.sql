-- Durable local analysis pipeline. PostgreSQL remains the source of truth.
ALTER TABLE event_outbox ADD COLUMN IF NOT EXISTS available_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE event_outbox ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ;
ALTER TABLE event_outbox ADD COLUMN IF NOT EXISTS last_error TEXT NOT NULL DEFAULT '';
UPDATE event_outbox SET kind = 'vision' WHERE kind = 'analyze-and-index';
CREATE UNIQUE INDEX IF NOT EXISTS event_outbox_event_kind_idx ON event_outbox (event_id, kind);
CREATE INDEX IF NOT EXISTS event_outbox_available_idx ON event_outbox (kind, status, available_at, id);

CREATE TABLE IF NOT EXISTS vision_analyses (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES events(event_id),
    description TEXT NOT NULL,
    model_name VARCHAR(200) NOT NULL,
    model_version VARCHAR(200) NOT NULL,
    prompt_version VARCHAR(100) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'completed',
    error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS vision_analyses_event_idx ON vision_analyses (event_id, id DESC);

CREATE TABLE IF NOT EXISTS risk_assessments (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES events(event_id),
    vision_analysis_id BIGINT NOT NULL REFERENCES vision_analyses(id),
    predicted_level VARCHAR(16) NOT NULL,
    probabilities JSONB NOT NULL,
    model_version VARCHAR(200) NOT NULL,
    model_checksum VARCHAR(128) NOT NULL,
    mapping_version VARCHAR(100) NOT NULL,
    threshold_policy_version VARCHAR(100) NOT NULL,
    mode VARCHAR(16) NOT NULL DEFAULT 'shadow',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (event_id, vision_analysis_id, model_version)
);
CREATE INDEX IF NOT EXISTS risk_assessments_event_idx ON risk_assessments (event_id, id DESC);

CREATE TABLE IF NOT EXISTS operator_tasks (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES events(event_id),
    risk_assessment_id BIGINT NOT NULL REFERENCES risk_assessments(id),
    mode VARCHAR(16) NOT NULL DEFAULT 'shadow',
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    operator_label VARCHAR(16),
    operator_note TEXT NOT NULL DEFAULT '',
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (risk_assessment_id, mode)
);
CREATE INDEX IF NOT EXISTS operator_tasks_pending_idx ON operator_tasks (mode, status, id DESC);
