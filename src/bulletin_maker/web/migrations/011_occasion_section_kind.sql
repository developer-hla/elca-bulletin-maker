-- Allow the church_texts store to hold per-section canonical_slot overrides.
--
-- A funeral / marriage rite's copyrighted sections are empty canonical_slots
-- filled at render time from the church's licensed Sundays & Seasons service.
-- When a section can't be auto-filled (unentitled, or the pull/parse drifts),
-- an admin enters the wording once; it is saved per church and reused every
-- service. That override reuses this table with kind='occasion_section',
-- name=<section_key>, body=<plain string>. Extend the kind CHECK to permit it.

ALTER TABLE church_texts DROP CONSTRAINT church_texts_kind_check;

ALTER TABLE church_texts ADD CONSTRAINT church_texts_kind_check CHECK (kind IN (
    'confession', 'offering_prayer', 'prayer_after_communion',
    'blessing', 'dismissal', 'prayer_of_day', 'occasion_section'
));
