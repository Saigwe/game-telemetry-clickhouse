import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RAW = ROOT / "data" / "raw"


@pytest.fixture(scope="session")
def ch():
    from pipeline.ch import client
    try:
        c = client()
        c.query("SELECT count() FROM game.rpt_checks")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"ClickHouse with built tables not reachable: {e}")
    return c


@pytest.fixture(scope="session")
def key():
    return json.loads((RAW / "answer_key.json").read_text(encoding="utf-8"))


def val(c, sql):
    return c.query(sql).result_rows[0][0]
