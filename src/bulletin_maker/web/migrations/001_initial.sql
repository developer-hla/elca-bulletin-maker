-- Initial schema for the PostgreSQL data layer.
-- Requires the citext extension (created out of band by the DBA / dev setup).

CREATE TABLE churches (
    id bigserial PRIMARY KEY,
    name text NOT NULL,
    invite_code text NOT NULL UNIQUE,
    profile_json jsonb NOT NULL,
    sns_username text NOT NULL DEFAULT '',
    sns_password_enc text NOT NULL DEFAULT '',
    plan text NOT NULL DEFAULT 'free',
    disabled boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id bigserial PRIMARY KEY,
    church_id bigint NOT NULL REFERENCES churches(id),
    email citext NOT NULL UNIQUE,
    password_hash text NOT NULL,
    display_name text NOT NULL DEFAULT '',
    role text NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    email_verified boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE past_runs (
    id text NOT NULL,
    church_id bigint NOT NULL REFERENCES churches(id),
    service_date text NOT NULL,
    timestamp timestamptz NOT NULL,
    metadata_json jsonb NOT NULL,
    form_data_json jsonb NOT NULL,
    PRIMARY KEY (church_id, id)
);

CREATE TABLE sessions (
    token_hash text PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE TABLE auth_tokens (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose text NOT NULL CHECK (purpose IN ('reset', 'magic', 'verify')),
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz
);

CREATE TABLE jobs (
    id text PRIMARY KEY,
    church_id bigint NOT NULL REFERENCES churches(id),
    user_id bigint REFERENCES users(id),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'done', 'failed')),
    progress_jsonb jsonb NOT NULL DEFAULT '[]',
    form_data_jsonb jsonb,
    errors_jsonb jsonb NOT NULL DEFAULT '{}',
    results_jsonb jsonb NOT NULL DEFAULT '{}',
    lease_expires timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE artifacts (
    id bigserial PRIMARY KEY,
    job_id text NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    doc_key text NOT NULL,
    filename text NOT NULL,
    object_key text NOT NULL,
    bytes bigint NOT NULL DEFAULT 0,
    expires_at timestamptz
);

CREATE TABLE sns_cache (
    cache_key text PRIMARY KEY,
    payload_jsonb jsonb,
    object_key text,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    ttl_seconds int NOT NULL DEFAULT 604800
);

CREATE TABLE plans (
    plan text PRIMARY KEY,
    limits_jsonb jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE audit_log (
    id bigserial PRIMARY KEY,
    actor_user_id bigint,
    church_id bigint,
    action text NOT NULL,
    detail_jsonb jsonb NOT NULL DEFAULT '{}',
    at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX past_runs_church_timestamp_idx
    ON past_runs (church_id, timestamp DESC);
CREATE INDEX sessions_user_idx ON sessions (user_id);
CREATE INDEX auth_tokens_user_purpose_idx ON auth_tokens (user_id, purpose);
CREATE INDEX jobs_church_created_idx ON jobs (church_id, created_at DESC);

INSERT INTO plans (plan, limits_jsonb) VALUES ('free', '{}');
