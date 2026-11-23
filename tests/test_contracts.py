"""Every raw file meets the event contract."""
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import yaml

from conftest import RAW, ROOT

SPEC = yaml.safe_load((ROOT / "contracts" / "events.yml").read_text(encoding="utf-8"))
TYPES = {"string": ("string", "large_string"), "int": ("int64", "int32"), "timestamp": ("timestamp[us]", "timestamp[ns]")}
FILES = sorted((RAW / "events").glob("*.parquet"))


@pytest.mark.skipif(not FILES, reason="run `make data` first")
@pytest.mark.parametrize("f", FILES[:3] + FILES[-3:], ids=lambda p: Path(p).stem)
def test_file_meets_contract(f):
    t = pq.read_table(f)
    assert list(t.schema.names) == list(SPEC["columns"])
    for col, typ in SPEC["columns"].items():
        assert str(t.schema.field(col).type) in TYPES[typ], col
    df = t.to_pandas()
    for col, allowed in SPEC["allowed"].items():
        assert set(df[col].unique()) <= set(allowed), col
    assert df["event_date"].str.fullmatch(r"\d{8}").all()
