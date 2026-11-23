/* Page renderers. Data: window.DASH (data.js). */
(function () {
  "use strict";
  const D = window.DASH;
  const { line, bar, card, table, fmt, esc } = window.Viz;
  const uniq = (a) => [...new Set(a)];
  const day = (s) => new Date(s.slice(0, 10) + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const B = ["3.4.0", "3.4.1", "3.5.0"];
  const P = ["android", "ios"];
  const PN = { android: "Android", ios: "iOS" };
  const rb = (p, b) => D.ret_build.find((r) => r.platform === p && r.build === b) || {};
  const cf = (p, b) => D.crash.find((r) => r.platform === p && r.build === b) || {};
  const chk = (n) => (D.checks.find((r) => r.check_name === n) || {}).value;
  const pts = (v) => (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(1) + " pts";
  const lvl = (p, b, t) => D.levels.filter((r) => r.platform === p && r.build === b && (!t || r.device_tier === t));
  function l7(p, b, t) { const r = lvl(p, b, t).filter((x) => x.level === 7); const s = r.reduce((a, x) => a + x.starts, 0); return s ? r.reduce((a, x) => a + x.crashes, 0) / s : null; }

  function tiles(list) {
    const el = document.getElementById("tiles");
    if (!el) return;
    el.replaceChildren(...list.map((t) => {
      const d = document.createElement("div"); d.className = "tile";
      const k = document.createElement("div"); k.className = "k"; k.textContent = t.k;
      const v = document.createElement("div"); v.className = "v"; v.textContent = t.v;
      d.append(k, v);
      if (t.d) { const s = document.createElement("div"); s.className = "d"; s.textContent = t.d; d.append(s); }
      return d;
    }));
  }
  const insights = (items) => {
    document.getElementById("insights").innerHTML = items.map(([cls, label, text, href, where]) =>
      `<li><span class="status ${cls}"><i aria-hidden="true">${cls === "good" ? "✓" : "!"}</i>${label}</span><span>${text} <a class="where" href="${href}">${where} →</a></span></li>`).join("");
  };
  const combined = (b, key) => { const rs = P.map((p) => rb(p, b)); const n = rs.reduce((a, r) => a + (r.d1_installs || 0), 0); return rs.reduce((a, r) => a + (r[key] || 0) * (r.d1_installs || 0), 0) / n; };

  function overview() {
    const ssOld = combined("3.4.1", "d1_session_start_rate"), ssNew = combined("3.5.0", "d1_session_start_rate");
    const aOld = combined("3.4.1", "d1_active_rate"), aNew = combined("3.5.0", "d1_active_rate");
    const resume = D.events.filter((r) => r.event_name === "app_resume").reduce((a, r) => a + r.events, 0);
    tiles([
      { k: "D1 on session_start, 3.4.1 → 3.5.0", v: pts(ssNew - ssOld), d: `${fmt.pct(1)(ssOld)} → ${fmt.pct(1)(ssNew)}: what the old dashboard showed` },
      { k: "D1 on any engagement", v: pts(aNew - aOld), d: `${fmt.pct(1)(aOld)} → ${fmt.pct(1)(aNew)}` },
      { k: "Android 3.5.0 D1", v: pts(rb("android", "3.5.0").d1_active_rate - rb("android", "3.4.1").d1_active_rate), d: "real: a crash" },
      { k: "iOS 3.5.0 D1", v: pts(rb("ios", "3.5.0").d1_active_rate - rb("ios", "3.4.1").d1_active_rate), d: "no real change" },
      { k: "Level-7 crash rate, Android low-memory 3.5.0", v: fmt.pct(0)(l7("android", "3.5.0", "low")), d: `against ${fmt.pct(1)(l7("android", "3.4.1", "low"))} on 3.4.1` },
    ]);
    insights([
      ["warning", "Mostly telemetry", `<b>On iOS the fall is a logging change, not players leaving.</b> From 3.5.0 a session resumed from the background is logged as a new event, <code>app_resume</code> (${fmt.int(resume)} so far), instead of <code>session_start</code>. D1 measured on session_start drops from ${fmt.pct(1)(rb("ios", "3.4.1").d1_session_start_rate)} to ${fmt.pct(1)(rb("ios", "3.5.0").d1_session_start_rate)}; measured on any engagement it is ${fmt.pct(1)(rb("ios", "3.4.1").d1_active_rate)} and ${fmt.pct(1)(rb("ios", "3.5.0").d1_active_rate)}.`, "instrumentation.html#in-events", "Instrumentation"],
      ["critical", "Real regression", `<b>On Android, 3.5.0 crashes at the start of level 7 on low-memory devices</b>: ${fmt.pct(0)(l7("android", "3.5.0", "low"))} of level-7 starts end in a fatal crash, against under 1% elsewhere. Crash-free sessions on Android 3.5.0 are ${fmt.pct(2)(cf("android", "3.5.0").crash_free_sessions)} against ${fmt.pct(2)(cf("android", "3.4.1").crash_free_sessions)} on 3.4.1, and D1 retention fell ${pts(rb("android", "3.5.0").d1_active_rate - rb("android", "3.4.1").d1_active_rate)}. Fix and ship a hotfix for low-memory Android.`, "progression.html", "Progression"],
      ["good", "Ruled out", `<b>Duplicates, missing builds and late data do not explain it.</b> ${fmt.int(chk("Duplicate deliveries removed"))} duplicate deliveries collapse on event_id (including a retry storm on 12 October), ${fmt.int(chk("Events with no build ID"))} events without a build are filled from their session, and the full backfill adds ${fmt.int(chk("Deliveries past the watermark (incremental run)"))} late deliveries.`, "instrumentation.html", "Instrumentation"],
      ["good", "Definitions", `<b>Crash-free sessions count sessions, not session_start events.</b> On iOS 3.5.0 the naive ratio understates sessions by the resumed ones; the declared denominator does not move.`, "stability.html", "Stability"],
    ]);
    const xs = [];
    P.forEach((p) => B.forEach((b) => xs.push(`${PN[p]} ${b}`)));
    const val = (k) => { const out = []; P.forEach((p) => B.forEach((b) => out.push(rb(p, b)[k] ?? null))); return out; };
    card("ov-ret", (el) => bar(el, { x: xs, yFmt: fmt.pct(0), yMin: 0, series: [{ name: "On session_start", data: val("d1_session_start_rate"), color: 1 }, { name: "Any engagement", data: val("d1_active_rate"), color: 0 }] }),
      { cols: [{ key: "platform", label: "Platform", fmt: (p) => PN[p] }, { key: "build", label: "Build" }, { key: "d1_installs", label: "Installs", fmt: fmt.int }, { key: "d1_session_start_rate", label: "D1 session_start", fmt: fmt.pct(1) }, { key: "d1_active_rate", label: "D1 any", fmt: fmt.pct(1) }], rows: D.ret_build });
    const combos = [["android", "high"], ["android", "low"], ["ios", "high"]];
    card("ov-l7", (el) => bar(el, { x: B, yFmt: fmt.pct(0), series: combos.map(([p, t], i) => ({ name: `${PN[p]}${p === "android" ? ", " + t + " memory" : ""}`, data: B.map((b) => l7(p, b, t)), color: i === 1 ? 1 : i === 0 ? 0 : 2 })) }),
      { cols: [{ key: "platform", label: "Platform", fmt: (p) => PN[p] }, { key: "build", label: "Build" }, { key: "device_tier", label: "Tier" }, { key: "starts", label: "Level-7 starts", fmt: fmt.int }, { key: "crashes", label: "Crashes", fmt: fmt.int }], rows: D.levels.filter((r) => r.level === 7) });
    card("ov-crashfree", (el) => bar(el, { x: B, yFmt: fmt.pct(1), yMin: 0.95, yMax: 1, series: P.map((p, i) => ({ name: PN[p], data: B.map((b) => cf(p, b).crash_free_sessions ?? null), color: i })) }),
      { cols: [{ key: "platform", label: "Platform", fmt: (p) => PN[p] }, { key: "build", label: "Build" }, { key: "sessions", label: "Sessions", fmt: fmt.int }, { key: "crashed_sessions", label: "Crashed", fmt: fmt.int }, { key: "crash_free_sessions", label: "Crash-free", fmt: fmt.pct(2) }], rows: D.crash });
  }

  function retention() {
    const days = uniq(D.ret_daily.map((r) => r.install_day)).sort();
    tiles(P.map((p) => ({ k: `${PN[p]} D1, 3.4.1 → 3.5.0`, v: pts(rb(p, "3.5.0").d1_active_rate - rb(p, "3.4.1").d1_active_rate), d: `${fmt.pct(1)(rb(p, "3.4.1").d1_active_rate)} → ${fmt.pct(1)(rb(p, "3.5.0").d1_active_rate)}` }))
      .concat([{ k: "Cohorts with a complete D7 window", v: String(D.ret_daily.length ? days.filter((d) => d <= "2026-10-24").length : 0), d: "install days to 24 October" }]));
    card("rt-daily", (el) => line(el, { x: days, xFmt: day, yFmt: fmt.pct(0), yMin: 0.3, yMax: 0.75, series: P.map((p, i) => ({ name: PN[p], data: days.map((d) => { const r = D.ret_daily.find((x) => x.install_day === d && x.platform === p); return r ? r.d1_active / r.installs : null; }), color: i })) }),
      { cols: [{ key: "install_day", label: "Install day" }, { key: "platform", label: "Platform", fmt: (p) => PN[p] }, { key: "installs", label: "Installs", fmt: fmt.int }, { key: "d1_active", label: "D1 active", fmt: fmt.int }, { key: "d1_session_start", label: "D1 session_start", fmt: fmt.int }], rows: D.ret_daily });
    table(document.getElementById("rtbuild"), [{ key: "platform", label: "Platform", fmt: (p) => PN[p] }, { key: "build", label: "Build" }, { key: "d1_installs", label: "D1 cohort", fmt: fmt.int }, { key: "d1_active_rate", label: "D1", fmt: fmt.pct(1) },
      { key: "d7_installs", label: "D7 cohort", fmt: fmt.int }, { key: "d7_active_rate", label: "D7", fmt: (v) => (v == null ? "–" : fmt.pct(1)(v)) }], D.ret_build);
    const at = D.ret_tier.filter((r) => r.platform === "android");
    card("rt-tier", (el) => bar(el, { x: B, yFmt: fmt.pct(0), yMin: 0, series: ["high", "low"].map((t, i) => ({ name: `${t} memory`, data: B.map((b) => (at.find((r) => r.build === b && r.device_tier === t) || {}).d1_active_rate ?? null), color: i })) }),
      { cols: [{ key: "build", label: "Build" }, { key: "device_tier", label: "Tier" }, { key: "installs", label: "Installs", fmt: fmt.int }, { key: "d1_active_rate", label: "D1", fmt: fmt.pct(1) }], rows: at });
    const cs = uniq(D.geo.map((r) => r.geo_country));
    table(document.getElementById("geo"), [{ key: "c", label: "Country" }].concat(B.map((b) => ({ key: b, label: b }))),
      cs.map((c) => Object.assign({ c }, Object.fromEntries(B.map((b) => { const r = D.geo.find((x) => x.geo_country === c && x.build === b); return [b, !r ? "" : r.is_suppressed ? "<50" : `${fmt.pct(1)(r.d1_active_rate)} (${fmt.int(r.installs)})`]; })))));
  }

  function stability() {
    tiles(P.map((p) => ({ k: `${PN[p]} 3.5.0 crash-free sessions`, v: fmt.pct(2)(cf(p, "3.5.0").crash_free_sessions), d: `3.4.1: ${fmt.pct(2)(cf(p, "3.4.1").crash_free_sessions)}` }))
      .concat([{ k: "Deferred crash reports", v: fmt.int(chk("Deferred crash reports")), d: `${fmt.int(chk("Crash reports outside the attribution window"))} outside 72 hours` }]));
    const xs = [], dec = [], nai = [];
    P.forEach((p) => B.forEach((b) => { xs.push(`${PN[p]} ${b}`); dec.push(cf(p, b).crash_free_sessions ?? null); nai.push(cf(p, b).naive_crash_free ?? null); }));
    card("st-build", (el) => bar(el, { x: xs, yFmt: fmt.pct(1), yMin: 0.95, yMax: 1, series: [{ name: "Declared: sessions", data: dec, color: 0 }, { name: "Naive: session_start events", data: nai, color: 1 }] }),
      { cols: [{ key: "platform", label: "Platform", fmt: (p) => PN[p] }, { key: "build", label: "Build" }, { key: "sessions", label: "Sessions", fmt: fmt.int }, { key: "crashed_sessions", label: "Crashed", fmt: fmt.int }, { key: "crash_free_sessions", label: "Crash-free", fmt: fmt.pct(2) },
        { key: "naive_session_starts", label: "session_start events", fmt: fmt.int }, { key: "naive_crash_events", label: "Crash events", fmt: fmt.int }, { key: "naive_crash_free", label: "Naive", fmt: fmt.pct(2) }], rows: D.crash });
    const days = uniq(D.daily.map((r) => r.session_day)).sort();
    card("st-daily", (el) => line(el, { x: days, xFmt: day, yFmt: (v) => Number(v).toFixed(1), yMin: 0, series: P.map((p, i) => ({ name: PN[p], data: days.map((d) => { const r = D.daily.find((x) => x.session_day === d && x.platform === p); return r ? (1000 * r.crashed_sessions) / r.sessions : null; }), color: i })) }),
      { cols: [{ key: "session_day", label: "Day" }, { key: "platform", label: "Platform", fmt: (p) => PN[p] }, { key: "sessions", label: "Sessions", fmt: fmt.int }, { key: "crashed_sessions", label: "Crashed", fmt: fmt.int }], rows: D.daily });
    const at = D.crash_tier.filter((r) => r.platform === "android");
    card("st-tier", (el) => bar(el, { x: B, yFmt: fmt.pct(1), yMin: 0.9, yMax: 1, series: ["high", "low"].map((t, i) => ({ name: `${t} memory`, data: B.map((b) => (at.find((r) => r.build === b && r.device_tier === t) || {}).crash_free_sessions ?? null), color: i })) }),
      { cols: [{ key: "build", label: "Build" }, { key: "device_tier", label: "Tier" }, { key: "sessions", label: "Sessions", fmt: fmt.int }, { key: "crash_free_sessions", label: "Crash-free", fmt: fmt.pct(2) }], rows: at });
  }

  function progression() {
    const levels = [...Array(12).keys()].map((i) => i + 1);
    const series = [["3.4.1", "low", 2], ["3.5.0", "high", 0], ["3.5.0", "low", 1]];
    const curve = (b, t) => { const r = lvl("android", b, t); const p1 = (r.find((x) => x.level === 1) || {}).players; return levels.map((L) => { const x = r.find((y) => y.level === L); return x && p1 ? (100 * x.players) / p1 : null; }); };
    tiles([
      { k: "Level-7 crash rate, Android 3.5.0 low memory", v: fmt.pct(0)(l7("android", "3.5.0", "low")), d: "per level start" },
      { k: "Same level, high memory", v: fmt.pct(1)(l7("android", "3.5.0", "high")), d: "Android 3.5.0" },
      { k: "Same level, iOS 3.5.0", v: fmt.pct(1)(l7("ios", "3.5.0", "high")), d: "no regression" },
    ]);
    card("pg-funnel", (el) => line(el, { x: levels, xFmt: (l) => "L" + l, yFmt: (v) => Number(v).toFixed(0), yMin: 0, series: series.map(([b, t, c]) => ({ name: `${b}, ${t} memory`, data: curve(b, t), color: c })) }),
      { cols: [{ key: "build", label: "Build" }, { key: "device_tier", label: "Tier" }, { key: "level", label: "Level" }, { key: "players", label: "Players", fmt: fmt.int }, { key: "starts", label: "Starts", fmt: fmt.int }, { key: "completes", label: "Completes", fmt: fmt.int }, { key: "crashes", label: "Crashes", fmt: fmt.int }], rows: D.levels.filter((r) => r.platform === "android") });
    card("pg-crash", (el) => bar(el, { x: levels, xFmt: (l) => "L" + l, yFmt: fmt.pct(0), series: ["high", "low"].map((t, i) => ({ name: `${t} memory`, data: levels.map((L) => { const x = lvl("android", "3.5.0", t).find((y) => y.level === L); return x && x.starts ? x.crashes / x.starts : null; }), color: i })) }),
      { cols: [{ key: "device_tier", label: "Tier" }, { key: "level", label: "Level" }, { key: "starts", label: "Starts", fmt: fmt.int }, { key: "crashes", label: "Crashes", fmt: fmt.int }], rows: lvl("android", "3.5.0") });
    const comp = levels.map((L) => { const r = D.levels.filter((x) => x.level === L); const s = r.reduce((a, x) => a + x.starts, 0); return s ? r.reduce((a, x) => a + x.completes, 0) / s : null; });
    card("pg-complete", (el) => bar(el, { x: levels, xFmt: (l) => "L" + l, yFmt: fmt.pct(0), yMin: 0, series: [{ name: "Completes per start", data: comp, color: 0 }] }),
      { cols: [{ key: "l", label: "Level" }, { key: "c", label: "Completion", fmt: fmt.pct(1) }], rows: levels.map((l, i) => ({ l, c: comp[i] })) });
  }

  function instrumentation() {
    tiles([
      { k: "Duplicate deliveries removed", v: fmt.int(chk("Duplicate deliveries removed")), d: "same event_id" },
      { k: "No build ID", v: fmt.int(chk("Events with no build ID")), d: `${fmt.int(chk("Events still with no build after filling"))} left after filling` },
      { k: "Out-of-order events", v: fmt.int(chk("Out-of-order events")), d: "client clock skew" },
      { k: "New event names", v: String(chk("New event names")), d: (D.checks.find((r) => r.check_name === "New event names") || {}).detail },
    ]);
    document.getElementById("checks").innerHTML = `<ul class="insights">${D.checks.map((r) => {
      const warn = /New event|outside|past the watermark|suppressed|still with no build/.test(r.check_name) && r.value > 0;
      return `<li><span class="status ${warn ? "warning" : "good"}"><i aria-hidden="true">${warn ? "!" : "✓"}</i>${warn ? "Flagged" : "Handled"}</span><span><b>${esc(r.check_name)}:</b> ${fmt.int(r.value)}. ${esc(r.detail)}.</span></li>`;
    }).join("")}</ul>`;
    const days = D.instr.map((r) => r.event_day);
    card("in-dups", (el) => bar(el, { x: days, xFmt: day, yFmt: fmt.int, series: [{ name: "Duplicate deliveries", data: D.instr.map((r) => r.duplicate_deliveries), colors: D.instr.map((r) => (r.event_day === "2026-10-12" ? 1 : 0)) }] }),
      { cols: [{ key: "event_day", label: "Day" }, { key: "unique_events", label: "Events", fmt: fmt.int }, { key: "deliveries_received", label: "Deliveries", fmt: fmt.int }, { key: "duplicate_deliveries", label: "Duplicates", fmt: fmt.int }], rows: D.instr });
    card("in-missing", (el) => bar(el, { x: days, xFmt: day, yFmt: fmt.int, series: [{ name: "No build ID", data: D.instr.map((r) => r.missing_build), color: 1 }] }),
      { cols: [{ key: "event_day", label: "Day" }, { key: "missing_build", label: "No build", fmt: fmt.int }, { key: "missing_build_unresolved", label: "Unresolved", fmt: fmt.int }], rows: D.instr });
    const names = ["session_start", "app_resume", "screen_view", "level_start"];
    const ios = D.events.filter((r) => r.platform === "ios");
    card("in-events", (el) => bar(el, { x: B, yFmt: fmt.int, series: names.map((n, i) => ({ name: n, data: B.map((b) => (ios.find((r) => r.event_name === n && r.app_version === b) || {}).events || 0), color: n === "app_resume" ? 1 : n === "session_start" ? 0 : i === 2 ? 2 : 3 })) }),
      { cols: [{ key: "event_name", label: "Event" }, { key: "app_version", label: "Build" }, { key: "first_seen", label: "First seen" }, { key: "events", label: "Events", fmt: fmt.int }, { key: "is_new_event", label: "New", fmt: (v) => (v ? "yes" : "") }], rows: ios });
  }

  function pipeline() {
    const snap = Object.fromEntries(D.snapshots.map((r) => [r.label, r]));
    tiles([
      { k: "Ingestion days processed", v: String(D.runs.length), d: `${fmt.int(D.runs.reduce((a, r) => a + r.partitions_rebuilt, 0))} day partitions rebuilt` },
      { k: "Rerun of the last day", v: snap.incremental && snap["incremental-rerun"] && snap.incremental.fingerprint === snap["incremental-rerun"].fingerprint ? "Identical" : "Changed", d: "idempotent" },
      { k: "Backfill adds", v: fmt.int((snap.full || {}).unique_events - (snap.incremental || {}).unique_events), d: "events only seen past the watermark" },
      { k: "ClickHouse", v: D.clickhouse_version.split(".").slice(0, 2).join("."), d: "server version in CI" },
    ]);
    card("pl-runs", (el) => bar(el, { x: D.runs.map((r) => r.processing_day), xFmt: day, yFmt: fmt.int, stack: true, series: [{ name: "Rebuilt (within watermark)", data: D.runs.map((r) => r.partitions_rebuilt), color: 0 }, { name: "Skipped (past watermark)", data: D.runs.map((r) => r.late_partitions_skipped), color: 1 }] }),
      { cols: [{ key: "processing_day", label: "Processing day" }, { key: "raw_rows_loaded", label: "Rows loaded", fmt: fmt.int }, { key: "partitions_rebuilt", label: "Rebuilt" }, { key: "late_partitions_skipped", label: "Skipped" }, { key: "seconds", label: "Seconds", fmt: fmt.num(1) }], rows: D.runs });
    card("pl-late", (el) => bar(el, { x: D.late.map((r) => r.event_day), xFmt: day, yFmt: fmt.int, series: [{ name: "Late deliveries", data: D.late.map((r) => r.deliveries), color: 1 }] }),
      { cols: [{ key: "event_day", label: "Event day" }, { key: "deliveries_received", label: "Deliveries", fmt: fmt.int }], rows: D.late });
    table(document.getElementById("snap"), [{ key: "label", label: "Run" }, { key: "unique_events", label: "Unique events", fmt: fmt.int }, { key: "sessions", label: "Session-days", fmt: fmt.int }, { key: "fingerprint", label: "Fingerprint", fmt: (v) => String(v).slice(-8) }], D.snapshots);
    const b = D.bench;
    document.getElementById("bench").innerHTML = !b ? "<p>No benchmark in this build.</p>" : `<ul class="insights">${b.results.map((r) =>
      `<li><span class="status good"><i aria-hidden="true">✓</i>${esc(r.query)}</span><span><b>${fmt.num(1)(r.median_ms)} ms median</b> (min ${fmt.num(1)(r.min_ms)}, max ${fmt.num(1)(r.max_ms)}, ${r.runs} runs)</span></li>`).join("")}
      <li><span class="status ${b.same_answer ? "good" : "critical"}"><i aria-hidden="true">${b.same_answer ? "✓" : "!"}</i>Answer</span><span>${b.same_answer ? "Both queries return identical results." : "The queries disagree."} ClickHouse ${esc(b.clickhouse_version)} on ${esc(b.machine)} (a GitHub-hosted runner in CI), ${fmt.int(b.raw_deliveries)} raw deliveries. Timings vary by machine; the queries are in <code>pipeline/benchmark.py</code>.</span></li></ul>`;
  }

  const PAGES = { overview, retention, stability, progression, instrumentation, pipeline };
  document.addEventListener("DOMContentLoaded", () => {
    if (!window.echarts) { document.querySelector("main").insertAdjacentHTML("afterbegin", '<p class="callout critical">Charts could not load (no network to the chart library). Tables still work.</p>'); }
    PAGES[document.body.dataset.page]();
  });
})();
