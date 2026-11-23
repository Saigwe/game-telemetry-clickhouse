"""Incremental processing, idempotency, the watermark, and definitions that hold whatever the data."""
from conftest import val


def snap(ch, label):
    return ch.query(f"SELECT unique_events, sessions, fingerprint FROM game.run_snapshots WHERE label = '{label}'").result_rows[0]


def test_rerun_is_idempotent(ch):
    assert snap(ch, "incremental") == snap(ch, "incremental-rerun")


def test_full_backfill_adds_exactly_the_late_events(ch):
    inc, full = snap(ch, "incremental")[0], snap(ch, "full")[0]
    late_only = val(ch, """SELECT uniqExact(event_id) FROM game.raw_events
                           WHERE event_id NOT IN (SELECT event_id FROM game.raw_events WHERE dateDiff('day', toDate(event_timestamp), ingest_date) <= 3)""")
    assert full - inc == late_only > 0


def test_one_row_per_event(ch):
    assert val(ch, "SELECT count() - uniqExact(event_id) FROM game.stg_events") == 0


def test_every_delivery_accounted_for(ch):
    assert val(ch, "SELECT sum(deliveries) FROM game.stg_events") == val(ch, "SELECT count() FROM game.raw_events")


def test_crash_free_uses_sessions_not_session_starts(ch):
    rows = ch.query("SELECT sessions, naive_session_starts FROM game.rpt_crash_free WHERE platform = 'ios' AND build = '3.5.0'").result_rows
    sessions, starts = rows[0]
    assert sessions > starts * 1.2


def test_crashed_sessions_never_exceed_sessions(ch):
    assert val(ch, "SELECT countIf(crashed_sessions > sessions) FROM game.rpt_crash_free") == 0


def test_retention_cohort_windows(ch):
    assert val(ch, "SELECT countIf(d7_complete AND install_day > toDate('2026-10-24')) FROM game.rpt_retention_daily") == 0
    assert val(ch, "SELECT countIf(d1_active_n > installs OR d7_active_n > installs) FROM game.rpt_retention_daily") == 0


def test_small_geo_cells_suppressed(ch):
    assert val(ch, "SELECT countIf(is_suppressed AND d1_active_rate IS NOT NULL) FROM game.rpt_geo") == 0
    assert val(ch, "SELECT countIf(is_suppressed) FROM game.rpt_geo") > 0


def test_schema_versions_both_map_levels(ch):
    assert val(ch, "SELECT countIf(event_name = 'level_start' AND level = 0) FROM game.stg_events") == 0
    assert val(ch, "SELECT uniqExact(schema_version) FROM game.stg_events WHERE event_name = 'level_start'") == 2
