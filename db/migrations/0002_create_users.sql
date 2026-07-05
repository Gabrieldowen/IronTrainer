-- Represents a person using the app (you or a friend) who has connected
-- their Strava account. Keyed by strava_athlete_id since that's the
-- stable identifier present on every webhook event and activity payload
-- — no separate mapping step needed when processing incoming data.
--
-- OAuth tokens (access_token, refresh_token, expires_at) are NOT stored
-- here yet — that's added in the OAuth commit, once we build the actual
-- connect flow. This table just establishes identity.

CREATE TABLE IF NOT EXISTS users (
    id                  BIGSERIAL PRIMARY KEY,
    strava_athlete_id   BIGINT NOT NULL UNIQUE,

    first_name          TEXT,
    last_name           TEXT,
    profile_picture_url TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();