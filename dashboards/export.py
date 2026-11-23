"""Collect what the dashboard pages show from the ClickHouse gold tables into one JSON document. Aggregates only.

Usage: python dashboards/export.py --out dashboards/site/data.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from pipeline.ch import client  # noqa: E402


def rows(c, sql: str) -> list[dict]:
    r = c.query(sql)
    out = []
    for row in r.result_rows:
        rec = {}
        for k, v in zip(r.column_names, row):
            if isinstance(v, (datetime, date)):
                v = v.isoformat()[:10]
            elif isinstance(v, (float, Decimal)):
                v = round(float(v), 6)
            elif isinstance(v, bool):
                v = bool(v)
            elif isinstance(v, list):
                v = list(v)
            rec[k] = v
        out.append(rec)
    return out


def collect(c) -> dict:
    d: dict = {}
    d["ret_build"] = rows(c, "SELECT * FROM game.rpt_retention_build ORDER BY platform, build")
    d["ret_daily"] = rows(c, """SELECT install_day, platform, sum(installs) AS installs, sum(d1_active_n) AS d1_active, sum(d1_session_start_n) AS d1_session_start
                                FROM game.rpt_retention_daily WHERE d1_complete GROUP BY install_day, platform ORDER BY install_day, platform""")
    d["ret_tier"] = rows(c, "SELECT * FROM game.rpt_retention_tier ORDER BY platform, build, device_tier")
    d["crash"] = rows(c, "SELECT * FROM game.rpt_crash_free ORDER BY platform, build")
    d["crash_tier"] = rows(c, "SELECT * FROM game.rpt_crash_free_tier ORDER BY platform, build, device_tier")
    d["daily"] = rows(c, """SELECT session_day, platform, sum(dau) AS dau, sum(sessions) AS sessions, sum(crashed_sessions) AS crashed_sessions
                            FROM game.rpt_daily GROUP BY session_day, platform ORDER BY session_day, platform""")
    d["levels"] = rows(c, """SELECT platform, build, device_tier, level, starts, players, completes, fails, crashes
                             FROM game.rpt_levels WHERE level <= 12 ORDER BY platform, build, device_tier, level""")
    d["geo"] = rows(c, "SELECT * FROM game.rpt_geo ORDER BY geo_country, build")
    d["events"] = rows(c, "SELECT * FROM game.rpt_events ORDER BY event_name, platform, app_version")
    d["instr"] = rows(c, "SELECT * FROM game.rpt_instrumentation_daily ORDER BY event_day")
    d["checks"] = rows(c, "SELECT * FROM game.rpt_checks")
    d["runs"] = rows(c, """SELECT processing_day, partitions_rebuilt, late_partitions_skipped, raw_rows_loaded, seconds
                           FROM game.pipeline_runs WHERE mode = 'incremental' ORDER BY processing_day""")
    d["snapshots"] = rows(c, "SELECT * FROM game.run_snapshots ORDER BY label")
    d["late"] = rows(c, "SELECT event_day, sum(deliveries) AS deliveries FROM game.late_beyond_watermark GROUP BY event_day ORDER BY event_day")
    d["clickhouse_version"] = c.query("SELECT version()").result_rows[0][0]
    bench = ROOT / "analysis" / "benchmark.json"
    d["bench"] = json.loads(bench.read_text(encoding="utf-8")) if bench.exists() else None
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "site" / "data.json"))
    a = ap.parse_args()
    data = collect(client())
    Path(a.out).write_text(json.dumps(data, separators=(",", ":"), default=str), encoding="utf-8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
