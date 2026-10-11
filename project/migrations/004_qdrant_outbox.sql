ALTER TABLE event_outbox ADD COLUMN IF NOT EXISTS revision BIGINT NOT NULL DEFAULT 1;
CREATE INDEX IF NOT EXISTS event_outbox_qdrant_idx
    ON event_outbox (kind, status, available_at, id)
    WHERE kind = 'qdrant';
