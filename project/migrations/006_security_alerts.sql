CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role VARCHAR(16) NOT NULL CHECK (role IN ('viewer', 'operator', 'supervisor')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash VARCHAR(64) PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    expires_at TIMESTAMPTZ NOT NULL,
    idle_expires_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS auth_sessions_expiry_idx ON auth_sessions (expires_at, idle_expires_at);

CREATE TABLE IF NOT EXISTS operator_decision_audit (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES operator_tasks(id),
    event_id UUID NOT NULL REFERENCES events(event_id),
    risk_assessment_id BIGINT NOT NULL REFERENCES risk_assessments(id),
    action VARCHAR(32) NOT NULL CHECK (action IN ('confirm', 'reject', 'label')),
    label VARCHAR(16),
    actor_user_id BIGINT NOT NULL REFERENCES users(id),
    actor_username VARCHAR(100) NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    previous_status VARCHAR(16) NOT NULL,
    new_status VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS operator_decision_audit_task_idx ON operator_decision_audit (task_id, id DESC);

CREATE TABLE IF NOT EXISTS model_releases (
    id BIGSERIAL PRIMARY KEY,
    version VARCHAR(200) NOT NULL UNIQUE,
    checksum VARCHAR(128) NOT NULL UNIQUE,
    model_card_hash VARCHAR(128) NOT NULL,
    mapping_version VARCHAR(100) NOT NULL,
    threshold_policy_version VARCHAR(100) NOT NULL,
    dataset_version VARCHAR(200) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'revoked')),
    registered_by VARCHAR(100) NOT NULL,
    approved_by VARCHAR(100),
    approved_at TIMESTAMPTZ,
    revoked_by VARCHAR(100),
    revoked_at TIMESTAMPTZ,
    revoke_reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS model_releases_one_approved_idx ON model_releases ((status)) WHERE status = 'approved';

CREATE TABLE IF NOT EXISTS model_evaluations (
    id BIGSERIAL PRIMARY KEY,
    release_id BIGINT NOT NULL REFERENCES model_releases(id),
    sample_count INTEGER NOT NULL CHECK (sample_count >= 0),
    macro_f1 DOUBLE PRECISION NOT NULL,
    high_recall DOUBLE PRECISION NOT NULL,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    language VARCHAR(16) NOT NULL DEFAULT 'ru',
    source VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS model_evaluations_release_idx ON model_evaluations (release_id, id DESC);
