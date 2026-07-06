-- Adds OAuth token storage directly to users, rather than a separate
-- table. Tokens rotate independently of profile data, but at this scale
-- that's a stylistic distinction, not a correctness one — keeping
-- everything about a connected account on one row is simpler to work
-- with going forward.
--
-- NOTE: refresh_token is stored in plaintext. If this grows beyond
-- trusted personal/friend use, encrypt this column at rest.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS access_token     TEXT,
    ADD COLUMN IF NOT EXISTS refresh_token    TEXT,
    ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS token_scope      TEXT;