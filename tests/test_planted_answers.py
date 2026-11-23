"""The pipeline finds what was planted, and only that."""
from conftest import val


def test_d1_retention_matches_ground_truth(ch, key):
    got = {f"{p}|{b}": round(r, 4) for p, b, r in ch.query("SELECT platform, build, sum(d1_active_n) / sum(installs) FROM game.rpt_retention_daily GROUP BY 1, 2").result_rows}
    assert got == key["d1_retention"]


def test_installs_match(ch, key):
    got = {f"{p}|{b}": n for p, b, n in ch.query("SELECT platform, build, count() FROM game.installs GROUP BY 1, 2").result_rows}
    assert got == key["installs"]


def test_real_regression_is_android_low_memory_level_7(ch):
    rows = ch.query("""SELECT platform, build, device_tier, crashes / starts FROM game.rpt_levels
                       WHERE level = 7 AND starts >= 50""").result_rows
    hot = [(p, b, t) for p, b, t, r in rows if r > 0.2]
    assert hot == [("android", "3.5.0", "low")]
    assert all(r < 0.03 for p, b, t, r in rows if (p, b, t) != ("android", "3.5.0", "low"))


def test_android_retention_really_fell_ios_did_not(ch):
    r = {(p, b): (a, s) for p, b, a, s in ch.query("SELECT platform, build, d1_active_rate, d1_session_start_rate FROM game.rpt_retention_build").result_rows}
    assert r[("android", "3.5.0")][0] < r[("android", "3.4.1")][0] - 0.02
    assert abs(r[("ios", "3.5.0")][0] - r[("ios", "3.4.1")][0]) < 0.04
    # measured on session_start, iOS 3.5.0 looks far worse: the logging change, not the players
    assert r[("ios", "3.5.0")][1] < r[("ios", "3.5.0")][0] - 0.1
    assert abs(r[("android", "3.5.0")][1] - r[("android", "3.5.0")][0]) < 0.01


def test_new_event_is_flagged(ch, key):
    got = [n for (n,) in ch.query("SELECT DISTINCT event_name FROM game.rpt_events WHERE is_new_event").result_rows]
    assert got == key["new_event_names"]
    assert val(ch, "SELECT groupUniqArray(platform) FROM game.rpt_events WHERE is_new_event") == ["ios"]


def test_duplicates_counted_and_removed(ch, key):
    assert val(ch, "SELECT count() FROM game.stg_events") == key["counts"]["events_true"]
    assert val(ch, "SELECT sum(deliveries) - count() FROM game.stg_events") == key["counts"]["duplicate_deliveries"]
    storm = val(ch, f"SELECT duplicate_deliveries FROM game.rpt_instrumentation_daily WHERE event_day = '{key['retry_storm_day']}'")
    assert storm == key["counts"]["duplicate_deliveries_storm_day"]


def test_missing_builds_filled(ch, key):
    assert val(ch, "SELECT countIf(app_version_raw = '') FROM game.stg_events") == key["counts"]["missing_build_events"]
    assert val(ch, "SELECT countIf(app_version = '') FROM game.stg_events") == 0


def test_out_of_order_detected(ch, key):
    # Planted skews are the floor; a skewed event can also make its successor look early,
    # so allow a small margin above the planted count.
    got = val(ch, "SELECT countIf(is_out_of_order) FROM game.stg_events")
    planted = key["counts"]["out_of_order"]
    assert planted <= got <= planted * 1.01 + 5


def test_deferred_crashes_and_window(ch, key):
    assert val(ch, "SELECT countIf(is_deferred) FROM game.fct_crashes") == key["counts"]["deferred_crash_reports"]
    assert val(ch, "SELECT countIf(NOT within_window) FROM game.fct_crashes") == key["counts"]["deferred_outside_window"]


def test_late_deliveries_past_watermark(ch, key):
    assert val(ch, "SELECT sum(deliveries) FROM game.late_beyond_watermark") == key["counts"]["late_events_over_3_days"]
