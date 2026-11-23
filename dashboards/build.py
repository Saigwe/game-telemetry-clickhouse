"""Write the dashboard pages and data.js. Run export.py first.

Usage: python dashboards/build.py [--data dashboards/site/data.json] [--site dashboards/site]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ECHARTS = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"
REPO = "https://github.com/Saigwe/game-telemetry-clickhouse"

PAGES = [
    ("index.html", "overview", "Overview"),
    ("retention.html", "retention", "Retention"),
    ("stability.html", "stability", "Stability"),
    ("progression.html", "progression", "Progression"),
    ("instrumentation.html", "instrumentation", "Instrumentation"),
    ("pipeline.html", "pipeline", "Pipeline"),
]


def card(cid, title, sub, src="", wide=False, tall=False, chart=True, extra=""):
    return f'''
    <section class="card{' wide' if wide else ''}" id="{cid}">
      <header><div><h2>{title}</h2><p class="sub">{sub}</p></div>{'<button class="tbl-btn" type="button" aria-pressed="false">Table</button>' if chart else ''}</header>
      {extra}{f'<div class="chart{" tall" if tall else ""}" role="img" aria-label="{title}"></div>' if chart else ''}
      <div class="table-view" hidden></div>
      <p class="src">{src or "Source: ClickHouse gold tables"}</p>
    </section>'''


def scope(text):
    return f'\n  <div class="filters"><span class="scope">{text}</span></div>'


G0, G1 = '\n  <div class="tiles" id="tiles"></div>\n  <div class="grid">', '\n  </div>'
SC = ("A fictional mobile puzzle game. Installs 1 September to 24 October 2026, events to 31 October. Build 3.5.0 released 6 October. "
      "Pseudonymous players, synthetic events. Retention cohorts by install day (UTC).")

BODIES = {
    "overview": ("Did build 3.5.0 hurt retention?",
                 "Day-1 retention measured the usual way fell after the release. Before acting, check whether the change is in the players or in the telemetry.",
                 scope(SC) + G0 +
                 card("ov-stories", "Verdict", "Each links to the evidence.", "Computed from every page", wide=True, chart=False, extra='<ul class="insights" id="insights"></ul>') +
                 card("ov-ret", "Day-1 retention by build: two definitions", "Session_start on day 1 against any engagement event on day 1", wide=True) +
                 card("ov-l7", "Crashes per level-7 start", "By build, platform and device memory tier") +
                 card("ov-crashfree", "Crash-free sessions by build", "Sessions = distinct session IDs; crashed = a fatal crash attributed to it") +
                 G1),
    "retention": ("Retention",
                  "D1 and D7 by install cohort, platform and build. A cohort counts only once its window has passed.",
                  scope("D1: the player engaged on the calendar day after install (UTC). D7: on the seventh day. 'Engaged' is any session, "
                        "screen or level event; the session_start definition is shown for comparison. Countries under 50 installs are suppressed.") + G0 +
                  card("rt-daily", "D1 retention by install day", "Any engagement; Android and iOS", wide=True) +
                  card("rt-build", "D1 and D7 by build", "Any engagement", chart=False, extra='<div id="rtbuild" class="table-view"></div>') +
                  card("rt-tier", "Android D1 by device memory tier", "The 3.5.0 fall is concentrated on low-memory devices") +
                  card("rt-geo", "D1 by country and build", "Cells under 50 installs suppressed", wide=True, chart=False, extra='<div id="geo" class="table-view"></div>') +
                  G1),
    "stability": ("Stability",
                  "Crash-free sessions by build and platform, with a declared denominator and crash attribution.",
                  scope("Sessions are distinct (player, session ID) pairs with at least one event. A crash reported on the next app open is "
                        "attributed to the session it happened in if it arrives within 72 hours; later reports are counted but not attributed.") + G0 +
                  card("st-build", "Crash-free sessions: declared against naive", "Naive = 1 - crash events / session_start events, from raw deliveries", wide=True) +
                  card("st-daily", "Crashed sessions per 1,000, by day", "Android and iOS") +
                  card("st-tier", "Crash-free by device memory tier", "Android builds") +
                  G1),
    "progression": ("Progression",
                    "Where players stop: level funnel and stage drop-off by build.",
                    scope("Starts, completes and fails per level from level events; schema 1 sends 'level', schema 2 'level_id', both mapped in staging. "
                          "Crashes are attributed to the last level started in the crashed session.") + G0 +
                    card("pg-funnel", "Players starting each level, Android", "Per 100 players starting level 1, by build and memory tier", wide=True) +
                    card("pg-crash", "Crashes per level start, Android 3.5.0", "By memory tier") +
                    card("pg-complete", "Completion rate per attempt", "Completes / starts, all builds") +
                    G1),
    "instrumentation": ("Instrumentation checks",
                        "Is a change in a metric a change in the players, or in the data? The checks that answer it.",
                        scope("Every check runs on every build of the pipeline. Duplicate deliveries share an event_id; a missing build is "
                              "filled from the session; out-of-order means a timestamp earlier than the previous event in client sequence.") + G0 +
                        card("in-checks", "Checks on the latest build", "From rpt_checks", wide=True, chart=False, extra='<div id="checks"></div>') +
                        card("in-dups", "Duplicate deliveries by event day", "SDK retries; one storm day") +
                        card("in-missing", "Events with no build ID by event day", "All filled from the session") +
                        card("in-events", "Events by name and build, iOS", "app_resume appears with 3.5.0 and session_start falls", wide=True) +
                        G1),
    "pipeline": ("Pipeline",
                 "Incremental daily processing with a watermark, idempotent reruns, a full backfill, and a measured benchmark.",
                 scope("Each ingestion day reloads its raw partition, then rebuilds only the event days it touched within a three-day watermark. "
                       "Older days are left alone and the late deliveries counted; the full backfill includes them.") + G0 +
                 card("pl-runs", "Partitions rebuilt per processing day", "Incremental run") +
                 card("pl-late", "Deliveries past the watermark, by event day", "Counted, kept in raw, picked up by the backfill") +
                 card("pl-snap", "Incremental, rerun and full backfill", "Unique events, session-days and a content fingerprint", chart=False, extra='<div id="snap" class="table-view"></div>') +
                 card("pl-bench", "Benchmark: D1 retention by build", "Same question from raw deliveries and from modelled tables; median of five runs", chart=False, extra='<div id="bench"></div>') +
                 G1),
}


def ver(site):
    h = hashlib.sha1()
    for f in ("assets/style.css", "assets/charts.js", "assets/pages.js", "data.js"):
        h.update((site / f).read_bytes())
    return h.hexdigest()[:10]


def page(key, v=""):
    title, lede, body = BODIES[key]
    nav = "".join(f'<a href="{f}"{" aria-current=page" if k == key else ""}>{label}</a>' for f, k, label in PAGES)
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Game telemetry on ClickHouse</title>
<meta name="description" content="Retention, crash-free sessions and progression for a fictional mobile game, with instrumentation checks, on ClickHouse and synthetic data.">
<link rel="stylesheet" href="assets/style.css?v={v}">
<script src="{ECHARTS}" defer></script>
<script src="assets/charts.js?v={v}" defer></script>
<script src="data.js?v={v}" defer></script>
<script src="assets/pages.js?v={v}" defer></script>
</head>
<body class="viz-root" data-page="{key}">
<div class="top"><div class="wrap">
  <div class="brand">Puzzle game telemetry <span>· ClickHouse · synthetic data</span></div>
  <nav class="tabs" aria-label="Dashboards">{nav}</nav>
  <button class="theme-btn" type="button">Dark mode</button>
</div></div>
<main class="wrap">
  <div class="page-head"><h1>{title}</h1><p>{lede}</p></div>
{body}
  <p class="footnote">The game, its players, builds and every number here are invented. Demo results, not any studio's figures.
  Built from ClickHouse tables by an incremental pipeline, rebuilt by CI on every change.
  Code: <a href="{REPO}">game-telemetry-clickhouse</a>. Built by <a href="https://saigwe.github.io">Stanley Igwe</a>.</p>
</main>
</body>
</html>
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "site" / "data.json"))
    ap.add_argument("--site", default=str(HERE / "site"))
    a = ap.parse_args()
    site = Path(a.site)
    data = json.loads(Path(a.data).read_text(encoding="utf-8"))
    (site / "data.js").write_text("window.DASH = " + json.dumps(data, separators=(",", ":")) + ";\n", encoding="utf-8")
    v = ver(site)
    for fname, key, _ in PAGES:
        (site / fname).write_text(page(key, v), encoding="utf-8", newline="\n")
    print(f"wrote {len(PAGES)} pages to {site}")


if __name__ == "__main__":
    main()
