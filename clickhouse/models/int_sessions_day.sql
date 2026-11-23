INSERT INTO game.int_sessions
SELECT
    event_day,
    user_id,
    session_id,
    any(platform),
    max(app_version),
    any(geo_country),
    any(device_tier),
    min(event_ts),
    max(event_ts),
    count(),
    countIf(event_name = 'session_start'),
    countIf(event_name = 'app_resume'),
    countIf(event_name = 'level_start'),
    argMaxIf(level, event_ts, event_name = 'level_start')
FROM game.stg_events
WHERE event_day = '{{ day }}'
GROUP BY event_day, user_id, session_id
