-- Per-church seasonal house-customs override scaffold (LWS-0d).
--
-- Bundled defaults for each LiturgicalSeason now live in
-- renderer/data/seasonal_customs.json (see renderer/season.py). This table
-- is the LWS-1+ hook for a church to override those defaults per season;
-- it is empty/unused today — get_church_seasonal_overrides() always
-- returns {} until a later workstream wires overrides into resolution.
--
-- rules holds a partial SeasonalConfig-shaped object (only the overridden
-- fields); church_id NULL is not meaningful here (every row is church-owned).

CREATE TABLE seasonal_rules (
    church_id bigint NOT NULL REFERENCES churches(id),
    season text NOT NULL,
    rules jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (church_id, season)
);
