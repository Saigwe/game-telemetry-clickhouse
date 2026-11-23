"""Orchestration example: load raw deliveries day by day, rebuild only the event days each load touches (within the
watermark), then rebuild gold.

  --mode incremental   process ingestion days in order with a three-day watermark (what runs every day)
  --mode full          rebuild every event day from all raw deliveries (the backfill; includes late events)
  --check-idempotent   after an incremental run, process the last day again and require identical results

Usage: python pipeline/run.py --mode incremental --check-idempotent
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.ch import SETTINGS, client, run_file  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "events"


def ingest_files() -> list[tuple[date, Path]]:
    out = []
    for f in sorted(RAW.glob("ingest_date=*.parquet")):
        out.append((date.fromisoformat(f.stem.split("=")[1]), f))
    return out


def load_raw(c, day: date, path: Path) -> int:
    df = pd.read_parquet(path)
    for col in ("event_timestamp", "ingested_at"):
        df[col] = pd.to_datetime(df[col]).dt.tz_localize("UTC")
    df["ingest_date"] = day
    c.command(f"ALTER TABLE game.raw_events DROP PARTITION '{day.isoformat()}'")
    c.insert_df("game.raw_events", df)
    return len(df)


def rebuild_day(c, event_day: date) -> None:
    for table in ("stg_events", "int_sessions"):
        c.command(f"ALTER TABLE game.{table} DROP PARTITION '{event_day.isoformat()}'")
    run_file(c, "models/stg_events_day.sql", ymd=event_day.strftime("%Y%m%d"))
    run_file(c, "models/int_sessions_day.sql", day=event_day.isoformat())


def fingerprint(c) -> tuple[int, int, int]:
    r = c.query("SELECT count(), (SELECT count() FROM game.int_sessions), sum(cityHash64(event_id, app_version, level, deliveries)) FROM game.stg_events").result_rows[0]
    return int(r[0]), int(r[1]), int(r[2])


def process_day(c, day: date, path: Path, mode: str) -> None:
    t0 = time.perf_counter()
    n = load_raw(c, day, path)
    touched = [d for (d,) in c.query(f"SELECT DISTINCT toDate(event_timestamp) FROM game.raw_events WHERE ingest_date = '{day}' ORDER BY 1").result_rows]
    watermark = day - timedelta(days=SETTINGS["lateness_days"])
    rebuilt = [d for d in touched if d >= watermark]
    skipped = [d for d in touched if d < watermark]
    for d in rebuilt:
        rebuild_day(c, d)
    if skipped:
        c.command(f"ALTER TABLE game.late_beyond_watermark DELETE WHERE processing_day = '{day}' SETTINGS mutations_sync = 2")
        c.command(f"""INSERT INTO game.late_beyond_watermark SELECT toDate('{day}'), toDate(event_timestamp), count()
                      FROM game.raw_events WHERE ingest_date = '{day}' AND toDate(event_timestamp) < toDate('{watermark}') GROUP BY 2""")
    c.insert("game.pipeline_runs", [[mode, day, n, len(rebuilt), len(skipped), time.perf_counter() - t0]],
             column_names=["mode", "processing_day", "raw_rows_loaded", "partitions_rebuilt", "late_partitions_skipped", "seconds"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["incremental", "full"], default="incremental")
    ap.add_argument("--check-idempotent", action="store_true")
    a = ap.parse_args()
    c = client()
    run_file(c, "schema.sql")
    files = ingest_files()
    if not files:
        sys.exit("no raw files: run `make data` first")

    if a.mode == "incremental":
        for table in ("raw_events", "stg_events", "int_sessions", "late_beyond_watermark", "pipeline_runs", "run_snapshots"):
            c.command(f"TRUNCATE TABLE game.{table}")
        for day, path in files:
            process_day(c, day, path, "incremental")
        u, s, fp = fingerprint(c)
        c.insert("game.run_snapshots", [["incremental", u, s, fp]], column_names=["label", "unique_events", "sessions", "fingerprint"])
        print(f"incremental: {len(files)} ingestion days, {u:,} unique events, {s:,} session-days")
        if a.check_idempotent:
            day, path = files[-1]
            process_day(c, day, path, "incremental-rerun")
            again = fingerprint(c)
            c.insert("game.run_snapshots", [["incremental-rerun", *again]], column_names=["label", "unique_events", "sessions", "fingerprint"])
            if again != (u, s, fp):
                sys.exit(f"not idempotent: {again} != {(u, s, fp)}")
            print("idempotent: reprocessing the last day changed nothing")
    else:
        if not c.query("SELECT count() FROM game.raw_events").result_rows[0][0]:
            for day, path in files:
                load_raw(c, day, path)
        t0 = time.perf_counter()
        days = [d for (d,) in c.query("SELECT DISTINCT toDate(event_timestamp) FROM game.raw_events ORDER BY 1").result_rows]
        for d in days:
            rebuild_day(c, d)
        u, s, fp = fingerprint(c)
        c.command("ALTER TABLE game.run_snapshots DELETE WHERE label = 'full' SETTINGS mutations_sync = 2")
        c.insert("game.run_snapshots", [["full", u, s, fp]], column_names=["label", "unique_events", "sessions", "fingerprint"])
        c.insert("game.pipeline_runs", [["full", days[-1], 0, len(days), 0, time.perf_counter() - t0]],
                 column_names=["mode", "processing_day", "raw_rows_loaded", "partitions_rebuilt", "late_partitions_skipped", "seconds"])
        print(f"full: {len(days)} event days rebuilt, {u:,} unique events")
    run_file(c, "gold.sql")
    print("gold rebuilt")


if __name__ == "__main__":
    main()
