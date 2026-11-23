"""ClickHouse connection and a tiny SQL runner. Settings from the environment (CH_HOST, CH_PORT, CH_USER, CH_PASSWORD)."""
from __future__ import annotations

import os
import re
from pathlib import Path

import clickhouse_connect

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "clickhouse"
SETTINGS = dict(attribution_hours=72, lateness_days=3, min_cell=50, last_day="2026-10-31",
                known_events="'first_open', 'session_start', 'screen_view', 'level_start', 'level_complete', 'level_fail', 'app_exception'")


def client():
    return clickhouse_connect.get_client(
        host=os.environ.get("CH_HOST", "localhost"), port=int(os.environ.get("CH_PORT", "8123")),
        username=os.environ.get("CH_USER", "default"), password=os.environ.get("CH_PASSWORD", ""),
        settings={"allow_suspicious_low_cardinality_types": 1})


def render(text: str, **params) -> str:
    values = {**SETTINGS, **params}
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(values[m.group(1)]), text)


def statements(text: str) -> list[str]:
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


def run_file(c, name: str, **params) -> None:
    for stmt in statements(render((SQL / name).read_text(encoding="utf-8"), **params)):
        c.command(stmt)
