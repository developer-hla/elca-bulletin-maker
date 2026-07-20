-- Rite engine storage (LWS-0b).
--
-- rites        — a full service order as structured block data.
-- rite_modules — reusable, occasion-scoped fragments (e.g. Holy Baptism)
--                referenced from a rite by a module_ref block.
--
-- church_id NULL = library row (shared/starter content owned by no church).
-- blocks/meta are jsonb; version bumps on every save; updated_at tracks it.
--
-- Later workstreams add church_texts (LWS-1), seasonal_rules (LWS-0d) and
-- lectionaries (LWS-3); none of those are created here.

CREATE TABLE rites (
    id text PRIMARY KEY,
    church_id bigint REFERENCES churches(id),   -- NULL = library rite
    name text NOT NULL,
    tradition text NOT NULL DEFAULT '',
    occasion text NOT NULL DEFAULT '',
    base_rite_id text REFERENCES rites(id),
    version int NOT NULL DEFAULT 1,
    blocks jsonb NOT NULL DEFAULT '[]',
    meta jsonb NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rite_modules (
    id text PRIMARY KEY,
    church_id bigint REFERENCES churches(id),   -- NULL = library module
    name text NOT NULL,
    version int NOT NULL DEFAULT 1,
    blocks jsonb NOT NULL DEFAULT '[]',
    meta jsonb NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- One rite per (church, occasion, name).  COALESCE folds library rows
-- (church_id NULL) into a single namespace so library uniqueness holds too
-- (plain UNIQUE would treat every NULL church_id as distinct).  church id
-- 0 is unused (bigserial starts at 1), so it is a safe library sentinel.
CREATE UNIQUE INDEX rites_scope_occasion_name_idx
    ON rites (COALESCE(church_id, 0), occasion, name);

CREATE UNIQUE INDEX rite_modules_scope_name_idx
    ON rite_modules (COALESCE(church_id, 0), name);

CREATE INDEX rites_church_idx ON rites (church_id);
CREATE INDEX rite_modules_church_idx ON rite_modules (church_id);
