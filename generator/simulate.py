"""Synthetic GA4-style telemetry for a fictional mobile puzzle game, written as one Parquet file per ingestion day.

The game ships build 3.5.0 on 6 October 2026 and day-1 retention appears to fall. Two things are planted:

* a real regression: on Android 3.5.0, low-memory devices crash at the start of level 7; players who crash come back
  less, so Android retention for 3.5.0 installs really does fall;
* an instrumentation change: on iOS 3.5.0, a session resumed from the background is logged as a new event,
  app_resume, instead of session_start. Retention measured on session_start falls on iOS; player behaviour did not change.

Plus what telemetry pipelines meet every day: SDK retries that duplicate event IDs (with a storm on 12 October),
events with no build ID, client clock skew that puts a level_complete before its level_start, offline play delivered
days late, a renamed event parameter (level -> level_id) in schema version 2, crash reports that arrive on the next
app open, and countries too small to publish.

Players are random pseudonymous IDs; there are no personal fields. answer_key.json records the planted truth.

Usage: python generator/simulate.py --out data/raw [--seed 41]
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

FIRST_DAY = date(2026, 9, 1)
LAST_INSTALL = date(2026, 10, 24)
LAST_DAY = date(2026, 10, 31)
INSTALLS_PER_DAY = 300
BUILDS = [("3.4.0", date(2026, 8, 18)), ("3.4.1", date(2026, 9, 22)), ("3.5.0", date(2026, 10, 6))]
RETRY_STORM = date(2026, 10, 12)
MISSING_BUILD_DAYS = (date(2026, 10, 15), date(2026, 10, 20))
ATTRIBUTION_HOURS = 72
COUNTRIES = ["US", "GB", "DE", "BR", "IN", "JP", "FR", "MX", "IS", "MT", "LU"]
COUNTRY_P = [0.30, 0.12, 0.10, 0.12, 0.14, 0.07, 0.07, 0.07, 0.003, 0.003, 0.004]
UTC = timezone.utc


def build_on(day: date) -> str:
    return [b for b, rel in BUILDS if rel <= day][-1]


def ts(d: date, seconds: float) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(seconds=float(seconds))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--seed", type=int, default=41)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    out = Path(a.out)
    if (out / "events").exists():
        shutil.rmtree(out / "events")
    out.mkdir(parents=True, exist_ok=True)
    total_c = np.array(COUNTRY_P) / sum(COUNTRY_P)

    rows = []                     # one tuple per delivered event
    seq = 0
    truth_sessions = []           # (platform, build, crashed_reported_in_window)
    truth_retention = defaultdict(lambda: [0, 0])   # (platform, install_build) -> [installs, retained_d1]
    level7 = defaultdict(lambda: [0, 0])             # (platform, build, tier) -> [level-7 starts, crashes]
    counts = defaultdict(int)

    def emit(user, sid, name, t, platform, build, country, tier, params, ingest_delay):
        nonlocal seq
        seq += 1
        schema = 2 if build >= "3.5.0" else 1
        rows.append((f"{seq:010d}", user, sid, name, t, platform, build, country, tier, schema, json.dumps(params, separators=(",", ":")), t + ingest_delay))

    n_days = (LAST_INSTALL - FIRST_DAY).days + 1
    uid = 0
    for di in range(n_days):
        iday = FIRST_DAY + timedelta(days=di)
        n_inst = int(rng.poisson(INSTALLS_PER_DAY))
        for _ in range(n_inst):
            uid += 1
            user = f"{rng.integers(16 ** 15):015x}.{1700000000 + uid}"
            platform = "android" if rng.random() < 0.6 else "ios"
            country = COUNTRIES[int(rng.choice(len(COUNTRIES), p=total_c))]
            tier = ("low" if rng.random() < 0.4 else "high") if platform == "android" else "high"
            engaged = rng.beta(2, 5)                      # how likely this player is to come back
            build = build_on(iday)
            install_build = build
            upgrade_lag = int(rng.geometric(0.25))
            level, first_session, last_crash = 1, True, None
            active_d1 = False
            crashed_day0 = False
            day = iday
            while day <= LAST_DAY:
                k = (day - iday).days
                newer = [b for b, rel in BUILDS if rel <= day - timedelta(days=upgrade_lag) and b > build]
                if newer:
                    build = newer[-1]
                if k == 0:
                    active = True
                else:
                    p = min(0.95, (0.55 * engaged / 0.286) * (0.80 ** (k - 1)) + 0.02)
                    if crashed_day0:
                        p *= 0.45
                    active = rng.random() < p
                if active:
                    if k == 1:
                        active_d1 = True
                    offline = rng.random() < 0.03
                    n_sess = 1 + int(rng.poisson(0.7))
                    starts = np.sort(rng.uniform(6 * 3600, 23.5 * 3600, n_sess))
                    for si, s0 in enumerate(starts):
                        t = ts(day, s0)
                        sid = int(t.timestamp())
                        delay_base = timedelta(days=float(rng.uniform(1, 6))) if offline else timedelta(seconds=0)
                        def d():
                            return delay_base + timedelta(seconds=float(rng.uniform(2, 120)))
                        if first_session:
                            emit(user, sid, "first_open", t, platform, build, country, tier, {}, d())
                        # a crash from an earlier session can be reported now, on the next open
                        if last_crash is not None:
                            c_sid, c_t, c_build = last_crash
                            within = (t - c_t) <= timedelta(hours=ATTRIBUTION_HOURS)
                            emit(user, sid, "app_exception", t, platform, build, country, tier,
                                 {"fatal": 1, "crashed_session_id": c_sid, "crash_ts": c_t.isoformat()}, d())
                            truth_sessions.append((platform, c_build, within))
                            counts["deferred_crash_reports"] += 1
                            counts["deferred_outside_window"] += 0 if within else 1
                            last_crash = None
                        resume = platform == "ios" and build >= "3.5.0" and not first_session and rng.random() < 0.6
                        emit(user, sid, "app_resume" if resume else "session_start", t, platform, build, country, tier, {}, d())
                        first_session = False
                        t += timedelta(seconds=float(rng.uniform(3, 10)))
                        emit(user, sid, "screen_view", t, platform, build, country, tier, {"screen": "map"}, d())
                        crashed = False
                        for _ in range(int(rng.integers(2, 7))):
                            t += timedelta(seconds=float(rng.uniform(5, 30)))
                            lv = {"level": level} if build < "3.5.0" else {"level_id": f"L{level:03d}"}
                            emit(user, sid, "level_start", t, platform, build, country, tier, lv, d())
                            p_crash = 0.004
                            if level == 7:
                                level7[(platform, build, tier)][0] += 1
                                if platform == "android" and build == "3.5.0" and tier == "low":
                                    p_crash = 0.45
                            if rng.random() < p_crash:
                                if level == 7:
                                    level7[(platform, build, tier)][1] += 1
                                ct = t + timedelta(seconds=float(rng.uniform(0.5, 4)))
                                if rng.random() < 0.85:
                                    emit(user, sid, "app_exception", ct, platform, build, country, tier, {"fatal": 1}, d())
                                    truth_sessions.append((platform, build, True))
                                else:
                                    last_crash = (sid, ct, build)
                                crashed = True
                                if k == 0:
                                    crashed_day0 = True
                                break
                            dur = float(rng.uniform(40, 180))
                            ok = rng.random() < max(0.35, 0.93 - 0.035 * level)
                            t_end = t + timedelta(seconds=dur)
                            if ok and rng.random() < 0.005:
                                t_end = t - timedelta(seconds=float(rng.uniform(1, 5)))      # client clock skew
                                counts["out_of_order"] += 1
                            emit(user, sid, "level_complete" if ok else "level_fail", t_end, platform, build, country, tier, lv, d())
                            t = max(t, t_end)
                            if ok:
                                level = min(level + 1, 30)
                        if crashed:
                            break
                day += timedelta(days=1)
            truth_retention[(platform, install_build)][0] += 1
            truth_retention[(platform, install_build)][1] += int(active_d1)

    cols = ["event_id", "user_pseudo_id", "ga_session_id", "event_name", "event_timestamp", "platform", "app_version",
            "geo_country", "device_tier", "schema_version", "event_params", "ingested_at"]
    df = pd.DataFrame(rows, columns=cols)
    counts["events_true"] = len(df)

    # SDK retries: the same event delivered again seconds later; a storm on one day.
    ev_day = df["event_timestamp"].dt.date
    p_dup = np.where(ev_day == RETRY_STORM, 0.25, 0.02)
    dup = df[rng.random(len(df)) < p_dup].copy()
    dup["ingested_at"] = dup["ingested_at"] + pd.to_timedelta(rng.uniform(1, 30, len(dup)), unit="s")
    counts["duplicate_deliveries"] = len(dup)
    counts["duplicate_deliveries_storm_day"] = int((dup["event_timestamp"].dt.date == RETRY_STORM).sum())

    # A third-party SDK path drops the build on some Android events for six days (never on session events).
    miss = ((df["platform"] == "android") & ev_day.between(*MISSING_BUILD_DAYS)
            & ~df["event_name"].isin(["session_start", "first_open", "app_resume"]) & (rng.random(len(df)) < 0.06))
    df.loc[miss, "app_version"] = ""
    dup_miss = df.loc[dup.index, "app_version"] == ""
    dup.loc[dup_miss[dup_miss].index, "app_version"] = ""
    counts["missing_build_events"] = int(miss.sum())

    allev = pd.concat([df, dup], ignore_index=True)
    allev["event_date"] = allev["event_timestamp"].dt.strftime("%Y%m%d")         # GA4 style, a string
    allev["ingest_date"] = allev["ingested_at"].dt.date
    allev = allev.sort_values(["ingested_at", "event_id"]).reset_index(drop=True)
    for c in ("event_timestamp", "ingested_at"):
        allev[c] = allev[c].dt.tz_convert("UTC").dt.tz_localize(None).astype("datetime64[us]")
    lateness = (allev["ingest_date"] - allev["event_timestamp"].dt.date).apply(lambda x: x.days)
    counts["late_events_over_3_days"] = int((lateness > 3).sum())

    (out / "events").mkdir(parents=True, exist_ok=True)
    order = ["event_id", "event_date", "event_timestamp", "event_name", "user_pseudo_id", "ga_session_id", "platform",
             "app_version", "geo_country", "device_tier", "schema_version", "event_params", "ingested_at"]
    for d_, part in allev.groupby("ingest_date"):
        part[order].to_parquet(out / "events" / f"ingest_date={d_.isoformat()}.parquet", index=False)

    # Ground truth
    key = dict(
        first_day=FIRST_DAY.isoformat(), last_install=LAST_INSTALL.isoformat(), last_day=LAST_DAY.isoformat(),
        release={"build": BUILDS[-1][0], "on": BUILDS[-1][1].isoformat()},
        attribution_hours=ATTRIBUTION_HOURS, lateness_days=3, retry_storm_day=RETRY_STORM.isoformat(),
        users=uid,
        d1_retention={f"{p}|{b}": round(r / n, 4) for (p, b), (n, r) in sorted(truth_retention.items()) if n},
        installs={f"{p}|{b}": n for (p, b), (n, r) in sorted(truth_retention.items())},
        level7_crash_rate={f"{p}|{b}|{t}": round(c / n, 4) for (p, b, t), (n, c) in sorted(level7.items()) if n >= 20},
        new_event_names=["app_resume"],
        counts=dict(counts),
    )
    (out / "answer_key.json").write_text(json.dumps(key, indent=1, default=str), encoding="utf-8")
    print(f"{uid:,} players, {len(df):,} events, {len(dup):,} duplicate deliveries, {allev['ingest_date'].nunique()} ingestion days")


if __name__ == "__main__":
    main()
