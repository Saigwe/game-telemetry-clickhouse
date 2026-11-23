# Design decisions

**Raw is append-only and partitioned by ingestion day.** Each day's deliveries land as received, duplicates included.
Reloading a day drops its partition first, so a rerun never doubles rows.

**Staging is partitioned by event day and rebuilt one day at a time.** A load touches only the event days present in
that day's deliveries. Each touched day is rebuilt from every delivery received so far (drop partition, insert),
which makes a rebuild idempotent: the same inputs always give the same partition.

**A three-day watermark.** Event days older than three days before the processing day are not rebuilt by the daily
run; their late deliveries are counted in `late_beyond_watermark` and stay in raw. The full backfill rebuilds every day
and picks them up. CI checks that the backfill adds exactly the events that had no delivery within three days.

**Deduplicate on the event ID, not on content.** SDK retries resend the same event; the copy keeps its `event_id`.
Staging keeps one row per ID and records how many deliveries it took.

**Fill a missing build from the session.** Every session opens with an event that carries the build; an event that lost
it takes its session's. Anything still unresolved is counted and left out of build comparisons.

**Map schema versions in one place.** Schema 1 sends `{"level": 7}`, schema 2 `{"level_id": "L007"}`. Staging maps
both to one `level` column; a test fails if any level event has no level.

**Out of order is judged by client sequence.** An event whose timestamp is earlier than the previous event's in client
order (`event_id`) is flagged, not reordered or dropped.

**Retention: install-day cohorts, calendar days, a declared event set.** D1 means engaged on the calendar day (UTC)
after the install day. "Engaged" is any session, screen or level event. The session_start definition is kept beside it
because it is what the old dashboard used, and the difference is the finding. A cohort counts only once its window
has passed.

**Crash-free sessions: the denominator is sessions.** A session is a distinct (player, session ID) pair. A crash is
attributed to the session it happened in, including crashes reported on the next app open, if the report arrives
within 72 hours. The naive ratio (crash events over session_start events) is shown for comparison.

**Gold is rebuilt in full.** The gold tables are small aggregates over staging; rebuilding them each run is simpler and
cheaper than incremental merges, and keeps them consistent with whatever partitions were rebuilt.

**Small cells are suppressed.** Country by build retention is not shown below 50 installs.

**The benchmark compares two ways to answer one question.** Day-1 retention by build, from raw deliveries
(deduplicating and parsing at query time) and from the modelled tables. Five timed runs after a warm-up, median kept,
query cache off, both answers compared for equality. Timings are machine-dependent and labelled with the machine.
