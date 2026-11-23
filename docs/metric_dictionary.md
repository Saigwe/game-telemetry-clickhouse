# Metric dictionary

| Metric | Definition | Grain | Table |
|---|---|---|---|
| **Install cohort** | Players whose first `first_open` falls on the day (UTC), with the platform and build of that event | install day x platform x build | `game.installs` |
| **D1 retention** | Share of a cohort engaged on install day + 1. Engaged = any of session_start, app_resume, screen_view, level_start, level_complete, level_fail | cohort | `game.rpt_retention_daily`, `rpt_retention_build` |
| **D1 retention (session_start)** | The same, counting only session_start; kept to show the logging change | cohort | same |
| **D7 retention** | Engaged on install day + 7; cohorts installed on or before 24 October only | cohort | same |
| **Session** | A distinct (player, ga_session_id) with at least one event | session | `game.sessions` |
| **Crash-free sessions** | 1 - sessions with an attributed fatal crash / sessions | platform x build (x tier, x day) | `game.rpt_crash_free` |
| **Attributed crash** | A fatal `app_exception`, assigned to the session it occurred in; deferred reports count if received within 72 hours | crash | `game.fct_crashes` |
| **Level starts, completes, fails** | Level events by level after mapping `level` and `level_id` | platform x build x tier x level | `game.rpt_levels` |
| **Crashes per level start** | Crashed sessions whose last level started is L, over starts of L | same | same |
| **Duplicate deliveries** | Deliveries minus unique event IDs | event day | `game.rpt_instrumentation_daily` |
| **Missing build** | Events delivered with no app_version; filled from the session | event day | same |
| **Late beyond watermark** | Deliveries whose event day was more than three days before their ingestion day | event day | `game.late_beyond_watermark` |

Small cells: country by build retention is suppressed below 50 installs.
