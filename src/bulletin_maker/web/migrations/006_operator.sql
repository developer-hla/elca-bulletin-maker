-- Cross-church service operators.
--
-- An operator is a user granted access to the operator console (the
-- service-owner's admin panel). The flag is per user, not per church.
--
-- The first operator is granted by hand, e.g.:
--   UPDATE users SET operator = true WHERE email = 'owner@example.org';

ALTER TABLE users ADD COLUMN operator boolean NOT NULL DEFAULT false;
