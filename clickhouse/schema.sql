CREATE DATABASE IF NOT EXISTS game;

-- Raw landing: one row per delivery, exactly as received. Partitioned by ingestion day so a day can be reloaded idempotently.
CREATE TABLE IF NOT EXISTS game.raw_events
(
    event_id String,
    event_date String,
    event_timestamp DateTime64(6, 'UTC'),
    event_name LowCardinality(String),
    user_pseudo_id String,
    ga_session_id Int64,
    platform LowCardinality(String),
    app_version LowCardinality(String),
    geo_country LowCardinality(String),
    device_tier LowCardinality(String),
    schema_version UInt8,
    event_params String,
    ingested_at DateTime64(6, 'UTC'),
    ingest_date Date
)
ENGINE = MergeTree
PARTITION BY ingest_date
ORDER BY (event_date, event_id);

-- Staging: one row per event ID, typed, build filled from the session, schema versions mapped. Partitioned by event day
-- so a late day can be rebuilt on its own.
CREATE TABLE IF NOT EXISTS game.stg_events
(
    event_day Date,
    event_id String,
    event_ts DateTime64(6, 'UTC'),
    event_name LowCardinality(String),
    user_id String,
    session_id Int64,
    platform LowCardinality(String),
    app_version LowCardinality(String),
    app_version_raw LowCardinality(String),
    geo_country LowCardinality(String),
    device_tier LowCardinality(String),
    schema_version UInt8,
    level UInt16,
    fatal UInt8,
    crashed_session_id Int64,
    crash_ts Nullable(DateTime64(6, 'UTC')),
    deliveries UInt32,
    first_ingested_at DateTime64(6, 'UTC'),
    lateness_days Int32,
    is_out_of_order UInt8
)
ENGINE = MergeTree
PARTITION BY event_day
ORDER BY (user_id, session_id, event_ts, event_id);

CREATE TABLE IF NOT EXISTS game.int_sessions
(
    event_day Date,
    user_id String,
    session_id Int64,
    platform LowCardinality(String),
    build LowCardinality(String),
    geo_country LowCardinality(String),
    device_tier LowCardinality(String),
    started_at DateTime64(6, 'UTC'),
    ended_at DateTime64(6, 'UTC'),
    events UInt32,
    session_starts UInt32,
    resumes UInt32,
    level_starts UInt32,
    last_level_started UInt16
)
ENGINE = MergeTree
PARTITION BY event_day
ORDER BY (user_id, session_id);

-- Events that arrived after the watermark had passed their day: kept in raw, left out of the daily models, counted here.
CREATE TABLE IF NOT EXISTS game.late_beyond_watermark
(
    processing_day Date,
    event_day Date,
    deliveries UInt64
)
ENGINE = MergeTree
ORDER BY (processing_day, event_day);

CREATE TABLE IF NOT EXISTS game.pipeline_runs
(
    run_at DateTime DEFAULT now(),
    mode LowCardinality(String),
    processing_day Date,
    raw_rows_loaded UInt64,
    partitions_rebuilt UInt32,
    late_partitions_skipped UInt32,
    seconds Float64
)
ENGINE = MergeTree
ORDER BY (run_at, processing_day);

CREATE TABLE IF NOT EXISTS game.run_snapshots
(
    label LowCardinality(String),
    unique_events UInt64,
    sessions UInt64,
    fingerprint UInt64
)
ENGINE = MergeTree
ORDER BY label;
