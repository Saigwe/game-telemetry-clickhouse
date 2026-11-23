-- Rebuild one event day of staging from every delivery received so far. Duplicate deliveries collapse on event_id.
INSERT INTO game.stg_events
    (event_day, event_id, event_ts, event_name, user_id, session_id, platform, app_version, app_version_raw, geo_country,
     device_tier, schema_version, level, fatal, crashed_session_id, crash_ts, deliveries, first_ingested_at, lateness_days, is_out_of_order)
WITH dedup AS
(
    SELECT
        event_id,
        any(event_timestamp) AS ts,
        any(event_name) AS name,
        any(user_pseudo_id) AS uid,
        any(ga_session_id) AS sid,
        any(platform) AS plat,
        any(app_version) AS ver_raw,
        any(geo_country) AS country,
        any(device_tier) AS tier,
        any(schema_version) AS schema,
        any(event_params) AS params,
        count() AS n_deliveries,
        min(ingested_at) AS first_ingested,
        min(ingest_date) AS first_ingest_day
    FROM game.raw_events
    WHERE event_date = '{{ ymd }}'
    GROUP BY event_id
)
SELECT
    toDate(ts) AS event_day,
    event_id,
    ts,
    name,
    uid,
    sid,
    plat,
    -- the build is on every session event; an event that lost it takes its session's
    if(ver_raw = '', max(ver_raw) OVER (PARTITION BY uid, sid), ver_raw),
    ver_raw,
    country,
    tier,
    schema,
    -- schema 1 sends {"level": 7}; schema 2 renamed it to {"level_id": "L007"}
    toUInt16(if(schema = 1, JSONExtractUInt(params, 'level'), toUInt16OrZero(substring(JSONExtractString(params, 'level_id'), 2)))),
    toUInt8(JSONExtractUInt(params, 'fatal')),
    JSONExtractInt(params, 'crashed_session_id'),
    parseDateTime64BestEffortOrNull(JSONExtractString(params, 'crash_ts'), 6, 'UTC'),
    n_deliveries,
    first_ingested,
    toInt32(dateDiff('day', toDate(ts), first_ingest_day)),
    -- the client sequence (event_id order) puts this event before an earlier timestamp: clock skew
    toUInt8(ts < lagInFrame(ts) OVER (PARTITION BY uid, sid ORDER BY event_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW))
FROM dedup
