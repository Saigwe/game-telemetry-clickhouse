-- Gold marts, rebuilt in full after the daily partitions (they are small). Statements are separated by blank-line semicolons.
DROP TABLE IF EXISTS game.sessions;
CREATE TABLE game.sessions ENGINE = MergeTree ORDER BY (user_id, session_id) AS
SELECT
    user_id,
    session_id,
    any(platform) AS platform,
    max(build) AS build,
    any(geo_country) AS geo_country,
    any(device_tier) AS device_tier,
    min(started_at) AS session_started_at,
    toDate(session_started_at) AS session_day,
    sum(events) AS events,
    sum(session_starts) AS session_starts,
    sum(resumes) AS resumes,
    argMax(last_level_started, ended_at) AS last_level_started
FROM game.int_sessions
GROUP BY user_id, session_id;

DROP TABLE IF EXISTS game.fct_crashes;
CREATE TABLE game.fct_crashes ENGINE = MergeTree ORDER BY (user_id, crashed_session_id) AS
SELECT
    user_id, event_id, reported_at, attributed_session AS crashed_session_id, crashed_at, is_deferred,
    dateDiff('second', crashed_at, reported_at) <= {{ attribution_hours }} * 3600 AS within_window
FROM
(
    SELECT
        user_id,
        event_id,
        event_ts AS reported_at,
        if(crashed_session_id != 0, crashed_session_id, session_id) AS attributed_session,
        if(crash_ts IS NULL, event_ts, assumeNotNull(crash_ts)) AS crashed_at,
        crashed_session_id != 0 AS is_deferred
    FROM game.stg_events
    WHERE event_name = 'app_exception' AND fatal = 1
);

DROP TABLE IF EXISTS game.session_outcomes;
CREATE TABLE game.session_outcomes ENGINE = MergeTree ORDER BY (user_id, session_id) AS
SELECT s.*, c.n > 0 AS crashed
FROM game.sessions AS s
LEFT JOIN
(
    SELECT user_id, crashed_session_id, count() AS n FROM game.fct_crashes WHERE within_window GROUP BY user_id, crashed_session_id
) AS c ON c.user_id = s.user_id AND c.crashed_session_id = s.session_id;

DROP TABLE IF EXISTS game.installs;
CREATE TABLE game.installs ENGINE = MergeTree ORDER BY user_id AS
SELECT
    user_id,
    toDate(min(event_ts)) AS install_day,
    argMin(platform, event_ts) AS platform,
    argMin(app_version, event_ts) AS build,
    argMin(geo_country, event_ts) AS geo_country,
    argMin(device_tier, event_ts) AS device_tier
FROM game.stg_events
WHERE event_name = 'first_open'
GROUP BY user_id;

DROP TABLE IF EXISTS game.user_days;
CREATE TABLE game.user_days ENGINE = MergeTree ORDER BY (user_id, event_day) AS
SELECT
    user_id,
    event_day,
    countIf(event_name IN ('session_start', 'app_resume', 'screen_view', 'level_start', 'level_complete', 'level_fail')) > 0 AS engaged,
    countIf(event_name = 'session_start') > 0 AS has_session_start
FROM game.stg_events
GROUP BY user_id, event_day;

DROP TABLE IF EXISTS game.user_retention;
CREATE TABLE game.user_retention ENGINE = MergeTree ORDER BY user_id AS
SELECT
    i.user_id AS user_id, i.install_day AS install_day, i.platform AS platform, i.build AS build,
    i.geo_country AS geo_country, i.device_tier AS device_tier,
    max(u.event_day = i.install_day + 1 AND u.engaged) AS d1_active,
    max(u.event_day = i.install_day + 1 AND u.has_session_start) AS d1_session_start,
    max(u.event_day = i.install_day + 7 AND u.engaged) AS d7_active,
    max(u.event_day = i.install_day + 7 AND u.has_session_start) AS d7_session_start
FROM game.installs AS i
LEFT JOIN game.user_days AS u ON u.user_id = i.user_id
GROUP BY i.user_id, i.install_day, i.platform, i.build, i.geo_country, i.device_tier;

DROP TABLE IF EXISTS game.rpt_retention_daily;
CREATE TABLE game.rpt_retention_daily ENGINE = MergeTree ORDER BY (install_day, platform, build) AS
SELECT
    install_day, platform, build,
    count() AS installs,
    sum(d1_active) AS d1_active_n,
    sum(d1_session_start) AS d1_session_start_n,
    sum(d7_active) AS d7_active_n,
    sum(d7_session_start) AS d7_session_start_n,
    install_day <= toDate('{{ last_day }}') - 1 AS d1_complete,
    install_day <= toDate('{{ last_day }}') - 7 AS d7_complete
FROM game.user_retention
GROUP BY install_day, platform, build;

DROP TABLE IF EXISTS game.rpt_retention_build;
CREATE TABLE game.rpt_retention_build ENGINE = MergeTree ORDER BY (platform, build) AS
SELECT
    platform, build,
    sumIf(installs, d1_complete) AS d1_installs,
    sumIf(d1_active_n, d1_complete) / sumIf(installs, d1_complete) AS d1_active_rate,
    sumIf(d1_session_start_n, d1_complete) / sumIf(installs, d1_complete) AS d1_session_start_rate,
    sumIf(installs, d7_complete) AS d7_installs,
    if(sumIf(installs, d7_complete) > 0, sumIf(d7_active_n, d7_complete) / sumIf(installs, d7_complete), NULL) AS d7_active_rate,
    if(sumIf(installs, d7_complete) > 0, sumIf(d7_session_start_n, d7_complete) / sumIf(installs, d7_complete), NULL) AS d7_session_start_rate
FROM game.rpt_retention_daily
GROUP BY platform, build;

DROP TABLE IF EXISTS game.rpt_retention_tier;
CREATE TABLE game.rpt_retention_tier ENGINE = MergeTree ORDER BY (platform, build, device_tier) AS
SELECT platform, build, device_tier, count() AS installs, avg(d1_active) AS d1_active_rate
FROM game.user_retention
WHERE install_day <= toDate('{{ last_day }}') - 1
GROUP BY platform, build, device_tier;

DROP TABLE IF EXISTS game.rpt_crash_free;
CREATE TABLE game.rpt_crash_free ENGINE = MergeTree ORDER BY (platform, build) AS
SELECT
    o.platform AS platform,
    o.build AS build,
    count() AS sessions,
    countIf(o.crashed) AS crashed_sessions,
    1 - countIf(o.crashed) / count() AS crash_free_sessions,
    any(n.crash_events) AS naive_crash_events,
    any(n.session_start_events) AS naive_session_starts,
    1 - any(n.crash_events) / any(n.session_start_events) AS naive_crash_free
FROM game.session_outcomes AS o
LEFT JOIN
(
    SELECT platform, app_version AS build, countIf(event_name = 'app_exception') AS crash_events, countIf(event_name = 'session_start') AS session_start_events
    FROM game.raw_events GROUP BY platform, build
) AS n ON n.platform = o.platform AND n.build = o.build
WHERE o.build != ''
GROUP BY o.platform, o.build;

DROP TABLE IF EXISTS game.rpt_crash_free_tier;
CREATE TABLE game.rpt_crash_free_tier ENGINE = MergeTree ORDER BY (platform, build, device_tier) AS
SELECT platform, build, device_tier, count() AS sessions, countIf(crashed) AS crashed_sessions, 1 - countIf(crashed) / count() AS crash_free_sessions
FROM game.session_outcomes WHERE build != ''
GROUP BY platform, build, device_tier;

DROP TABLE IF EXISTS game.rpt_daily;
CREATE TABLE game.rpt_daily ENGINE = MergeTree ORDER BY (session_day, platform, build) AS
SELECT session_day, platform, build, uniqExact(user_id) AS dau, count() AS sessions, countIf(crashed) AS crashed_sessions
FROM game.session_outcomes WHERE build != ''
GROUP BY session_day, platform, build;

DROP TABLE IF EXISTS game.rpt_levels;
CREATE TABLE game.rpt_levels ENGINE = MergeTree ORDER BY (platform, build, device_tier, level) AS
SELECT
    e.platform AS platform, e.app_version AS build, e.device_tier AS device_tier, e.level AS level,
    countIf(e.event_name = 'level_start') AS starts,
    uniqExactIf(e.user_id, e.event_name = 'level_start') AS players,
    countIf(e.event_name = 'level_complete') AS completes,
    countIf(e.event_name = 'level_fail') AS fails,
    any(c.crashes) AS crashes
FROM game.stg_events AS e
LEFT JOIN
(
    SELECT platform, build, device_tier, last_level_started AS level, countIf(crashed) AS crashes
    FROM game.session_outcomes GROUP BY platform, build, device_tier, level
) AS c ON c.platform = e.platform AND c.build = e.app_version AND c.device_tier = e.device_tier AND c.level = e.level
WHERE e.level BETWEEN 1 AND 15 AND e.app_version != ''
GROUP BY e.platform, e.app_version, e.device_tier, e.level;

DROP TABLE IF EXISTS game.rpt_geo;
CREATE TABLE game.rpt_geo ENGINE = MergeTree ORDER BY (geo_country, build) AS
SELECT
    geo_country, build,
    count() AS installs,
    count() < {{ min_cell }} AS is_suppressed,
    if(count() < {{ min_cell }}, NULL, avg(d1_active)) AS d1_active_rate
FROM game.user_retention
WHERE install_day <= toDate('{{ last_day }}') - 1
GROUP BY geo_country, build;

DROP TABLE IF EXISTS game.rpt_events;
CREATE TABLE game.rpt_events ENGINE = MergeTree ORDER BY (event_name, platform, app_version) AS
SELECT event_name, platform, app_version, min(event_day) AS first_seen, count() AS events,
       event_name NOT IN ({{ known_events }}) AS is_new_event
FROM game.stg_events
GROUP BY event_name, platform, app_version;

DROP TABLE IF EXISTS game.rpt_instrumentation_daily;
CREATE TABLE game.rpt_instrumentation_daily ENGINE = MergeTree ORDER BY event_day AS
SELECT
    event_day,
    count() AS unique_events,
    sum(deliveries) AS deliveries_received,
    deliveries_received - unique_events AS duplicate_deliveries,
    countIf(app_version_raw = '') AS missing_build,
    countIf(app_version_raw = '' AND app_version = '') AS missing_build_unresolved,
    countIf(is_out_of_order) AS out_of_order,
    countIf(lateness_days >= 1) AS arrived_late,
    countIf(schema_version = 2) AS schema_v2_events,
    countIf(event_name = 'level_start' AND level = 0) AS level_start_without_level
FROM game.stg_events
GROUP BY event_day;

DROP TABLE IF EXISTS game.rpt_checks;
CREATE TABLE game.rpt_checks ENGINE = MergeTree ORDER BY check_name AS
SELECT 'Deliveries received' AS check_name, toFloat64(count()) AS value, 'raw_events rows' AS detail FROM game.raw_events
UNION ALL SELECT 'Unique events', toFloat64(count()), 'stg_events rows, one per event_id' FROM game.stg_events
UNION ALL SELECT 'Duplicate deliveries removed', toFloat64(sum(deliveries) - count()), 'same event_id delivered again by SDK retries' FROM game.stg_events
UNION ALL SELECT 'Events with no build ID', toFloat64(countIf(app_version_raw = '')), 'filled from the session' FROM game.stg_events
UNION ALL SELECT 'Events still with no build after filling', toFloat64(countIf(app_version = '')), 'left out of build comparisons' FROM game.stg_events
UNION ALL SELECT 'Out-of-order events', toFloat64(countIf(is_out_of_order)), 'timestamp earlier than the previous event in client sequence' FROM game.stg_events
UNION ALL SELECT 'Level events missing a level', toFloat64(countIf(event_name IN ('level_start', 'level_complete', 'level_fail') AND level = 0)), 'after mapping level and level_id' FROM game.stg_events
UNION ALL SELECT 'New event names', toFloat64(uniqExactIf(event_name, is_new_event)), arrayStringConcat(groupUniqArrayIf(event_name, is_new_event), ', ') FROM game.rpt_events
UNION ALL SELECT 'Deferred crash reports', toFloat64(countIf(is_deferred)), 'reported on the next app open' FROM game.fct_crashes
UNION ALL SELECT 'Crash reports outside the attribution window', toFloat64(countIf(NOT within_window)), 'more than {{ attribution_hours }} hours after the crash, not attributed' FROM game.fct_crashes
UNION ALL SELECT 'Deliveries past the watermark (incremental run)', toFloat64(sum(deliveries)), 'more than {{ lateness_days }} days late, included by the full backfill' FROM game.late_beyond_watermark
UNION ALL SELECT 'Country x build cells suppressed', toFloat64(countIf(is_suppressed)), 'fewer than {{ min_cell }} installs' FROM game.rpt_geo
