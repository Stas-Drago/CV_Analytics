CREATE TABLE IF NOT EXISTS events (
    event_id UUID PRIMARY KEY,
    camera_id VARCHAR(100) NOT NULL,
    track_id VARCHAR(100) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    object_type VARCHAR(100) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    bbox JSONB NOT NULL,
    description TEXT,
    risk_level VARCHAR(16),
    risk_probability JSONB,
    risk_rationale TEXT NOT NULL DEFAULT '',
    media_uri TEXT NOT NULL DEFAULT '',
    frame_data BYTEA NOT NULL,
    object_crop BYTEA,
    frame_media_type VARCHAR(50) NOT NULL DEFAULT 'image/jpeg',
    model_version VARCHAR(100) NOT NULL,
    alert_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    operator_note TEXT NOT NULL DEFAULT ''
    ,deduplication_key VARCHAR(255) NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS events_occurred_at_idx ON events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS events_object_type_idx ON events (object_type);
