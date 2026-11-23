"""A repeatable performance comparison: the same question (day-1 retention by platform and build) answered from the raw
deliveries and from the modelled tables. Explicit queries, five timed runs each after one warm-up; the median is kept.
Timings depend on the machine; CI records them on a GitHub-hosted runner.

Usage: python pipeline/benchmark.py --out analysis/benchmark.json
"""
from __future__ import annotations

import argparse
import json
import platform as pf
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.ch import SETTINGS, client  # noqa: E402

QUERIES = {
    "raw deliveries": f"""
WITH ev AS (
    SELECT event_id, any(user_pseudo_id) AS u, any(platform) AS p, any(app_version) AS v, any(event_name) AS n,
           toDate(any(event_timestamp)) AS d
    FROM game.raw_events GROUP BY event_id
), inst AS (
    SELECT u, min(d) AS install_day, argMin(p, d) AS p, argMin(v, d) AS v FROM ev WHERE n = 'first_open' GROUP BY u
), act AS (
    SELECT DISTINCT u, d FROM ev WHERE n IN ('session_start', 'app_resume', 'screen_view', 'level_start', 'level_complete', 'level_fail')
)
SELECT p, v, count() AS installs, avg(retained) AS d1
FROM (SELECT i.u, any(i.p) AS p, any(i.v) AS v, max(a.d = i.install_day + 1) AS retained
      FROM inst AS i LEFT JOIN act AS a ON a.u = i.u
      WHERE i.install_day <= toDate('{SETTINGS["last_day"]}') - 1 GROUP BY i.u)
GROUP BY p, v ORDER BY p, v""",
    "modelled tables": f"""
SELECT platform, build, count() AS installs, avg(d1_active) AS d1
FROM game.user_retention WHERE install_day <= toDate('{SETTINGS["last_day"]}') - 1
GROUP BY platform, build ORDER BY platform, build""",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="analysis/benchmark.json")
    ap.add_argument("--runs", type=int, default=5)
    a = ap.parse_args()
    c = client()
    results, answers = [], {}
    rows_raw = c.query("SELECT count() FROM game.raw_events").result_rows[0][0]
    for name, sql in QUERIES.items():
        answers[name] = [tuple(round(float(x), 6) if isinstance(x, float) else x for x in r) for r in c.query(sql).result_rows]
        times = []
        for _ in range(a.runs):
            t0 = time.perf_counter()
            c.query(sql, settings={"use_query_cache": 0})
            times.append((time.perf_counter() - t0) * 1000)
        results.append({"query": name, "median_ms": round(statistics.median(times), 1), "min_ms": round(min(times), 1),
                        "max_ms": round(max(times), 1), "runs": a.runs, "sql": sql.strip()})
    same = answers["raw deliveries"] == answers["modelled tables"]
    version = c.query("SELECT version()").result_rows[0][0]
    doc = {"clickhouse_version": version, "machine": f"{pf.system()} {pf.machine()}", "raw_deliveries": rows_raw,
           "same_answer": same, "results": results}
    Path(a.out).write_text(json.dumps(doc, indent=1), encoding="utf-8")
    timings = ", ".join("{} {} ms".format(r["query"], r["median_ms"]) for r in results)
    print(f"benchmark: {timings}; same answer: {same}")
    if not same:
        sys.exit("the two queries disagree")


if __name__ == "__main__":
    main()
