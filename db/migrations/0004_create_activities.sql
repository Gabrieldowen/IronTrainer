CREATE TABLE IF NOT EXISTS activities (
    id                              BIGSERIAL PRIMARY KEY,

    strava_activity_id              BIGINT NOT NULL UNIQUE,
    athlete_id                      BIGINT NOT NULL REFERENCES users (strava_athlete_id),

    name                            TEXT NOT NULL,
    description                     TEXT,
    activity_type                   TEXT NOT NULL,
    sport_type                      TEXT,
    workout_type                    INTEGER,

    distance_meters                 DOUBLE PRECISION,
    moving_time_seconds             INTEGER,
    elapsed_time_seconds            INTEGER,
    total_elevation_gain_meters     DOUBLE PRECISION,
    elev_high_meters                DOUBLE PRECISION,
    elev_low_meters                 DOUBLE PRECISION,

    start_date                      TIMESTAMPTZ NOT NULL,
    start_date_local                TIMESTAMPTZ,
    timezone                        TEXT,

    average_speed_mps               DOUBLE PRECISION,
    max_speed_mps                   DOUBLE PRECISION,
    average_heartrate               DOUBLE PRECISION,
    max_heartrate                   DOUBLE PRECISION,
    has_heartrate                   BOOLEAN NOT NULL DEFAULT false,
    average_cadence                 DOUBLE PRECISION,
    average_watts                   DOUBLE PRECISION,
    max_watts                       DOUBLE PRECISION,
    weighted_average_watts          DOUBLE PRECISION,
    device_watts                    BOOLEAN NOT NULL DEFAULT false,
    kilojoules                      DOUBLE PRECISION,
    calories                        DOUBLE PRECISION,
    suffer_score                    INTEGER,
    perceived_exertion              INTEGER,

    start_lat                       DOUBLE PRECISION,
    start_lng                       DOUBLE PRECISION,
    end_lat                         DOUBLE PRECISION,
    end_lng                         DOUBLE PRECISION,
    map_polyline                    TEXT,

    gear_id                         TEXT,

    achievement_count               INTEGER,
    kudos_count                     INTEGER,
    comment_count                   INTEGER,
    athlete_count                   INTEGER,
    photo_count                     INTEGER,

    trainer                         BOOLEAN NOT NULL DEFAULT false,
    commute                         BOOLEAN NOT NULL DEFAULT false,
    manual                          BOOLEAN NOT NULL DEFAULT false,
    private                         BOOLEAN NOT NULL DEFAULT false,
    flagged                         BOOLEAN NOT NULL DEFAULT false,

    raw_json                        JSONB NOT NULL,

    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_activities_athlete_id
    ON activities (athlete_id);

CREATE INDEX IF NOT EXISTS idx_activities_start_date
    ON activities (start_date DESC);

CREATE INDEX IF NOT EXISTS idx_activities_type
    ON activities (activity_type);

CREATE TRIGGER trg_activities_updated_at
    BEFORE UPDATE ON activities
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();