CREATE TABLE IF NOT EXISTS strava_events (
    id              BIGSERIAL PRIMARY KEY,

    object_type     TEXT NOT NULL,
    aspect_type     TEXT NOT NULL,
    object_id       BIGINT NOT NULL,
    owner_id        BIGINT NOT NULL,

    raw_payload     JSONB NOT NULL,

    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at    TIMESTAMPTZ,
    processing_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_strava_events_unprocessed
    ON strava_events (received_at)
    WHERE processed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_strava_events_object_id
    ON strava_events (object_type, object_id);