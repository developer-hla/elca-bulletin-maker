-- Persistent per-church liturgical-text library (LWS-1).
--
-- Today a volunteer's custom edits to the 6 liturgical-text fields (prayer
-- of day, confession, offering prayer, prayer after communion, blessing,
-- dismissal) vanish at the end of the week. This table lets a church save a
-- named custom text once per field and reuse it — the wizard's dropdown for
-- each field grows a "your saved texts" section alongside S&S/house presets.
--
-- kind matches a build_liturgical_text_options() field key. body mirrors how
-- ServiceConfig carries that field: a plain string for the single-text kinds
-- (offering_prayer, prayer_after_communion, blessing, prayer_of_day), or a
-- [{role, text}] dialogue list for the two structured kinds (confession,
-- dismissal) — the same shape build_liturgical_text_options() already
-- returns and service_form.parse_dialog_entries() already reads.

CREATE TABLE church_texts (
    id bigserial PRIMARY KEY,
    church_id bigint NOT NULL REFERENCES churches(id),
    kind text NOT NULL CHECK (kind IN (
        'confession', 'offering_prayer', 'prayer_after_communion',
        'blessing', 'dismissal', 'prayer_of_day'
    )),
    name text NOT NULL,
    body jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX church_texts_scope_idx
    ON church_texts (church_id, kind, name);

CREATE INDEX church_texts_church_idx ON church_texts (church_id);
