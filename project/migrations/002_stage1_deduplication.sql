-- Upgrade installations created by the legacy SQLAlchemy schema and create outbox.
ALTER TABLE events ALTER COLUMN event_id TYPE UUID USING event_id::uuid;
ALTER TABLE events ALTER COLUMN bbox TYPE JSONB USING bbox::jsonb;
ALTER TABLE events ALTER COLUMN risk_probability TYPE JSONB USING to_jsonb(risk_probability);
ALTER TABLE events ADD COLUMN IF NOT EXISTS media_uri TEXT NOT NULL DEFAULT '';
ALTER TABLE events ADD COLUMN IF NOT EXISTS risk_rationale TEXT NOT NULL DEFAULT '';
ALTER TABLE events ADD COLUMN IF NOT EXISTS frame_data BYTEA;
UPDATE events SET frame_data = decode('', 'hex') WHERE frame_data IS NULL;
ALTER TABLE events ALTER COLUMN frame_data SET NOT NULL;
ALTER TABLE events ADD COLUMN IF NOT EXISTS object_crop BYTEA;
ALTER TABLE events ADD COLUMN IF NOT EXISTS frame_media_type VARCHAR(50) NOT NULL DEFAULT 'image/jpeg';
ALTER TABLE events ADD COLUMN IF NOT EXISTS deduplication_key VARCHAR(255);
UPDATE events
SET deduplication_key = 'legacy:' || event_id::text
WHERE deduplication_key IS NULL;
ALTER TABLE events ALTER COLUMN deduplication_key SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS events_deduplication_key_idx ON events (deduplication_key);

CREATE TABLE IF NOT EXISTS event_outbox (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES events(event_id),
    kind VARCHAR(32) NOT NULL DEFAULT 'analyze-and-index',
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS event_outbox_pending_idx ON event_outbox (status, id);
