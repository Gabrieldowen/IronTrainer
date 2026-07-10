-- Links a users row to a Discord account. Populated when a user runs the
-- bot's !connect command and completes the Strava OAuth flow — the
-- Discord user ID is passed through as the OAuth `state` parameter and
-- read back in the callback.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS discord_id BIGINT UNIQUE;