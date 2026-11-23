"""Same seed, same data; no personal fields."""
import hashlib
import subprocess
import sys

import pandas as pd

from conftest import ROOT


def test_same_seed_same_data(tmp_path):
    for run in ("a", "b"):
        subprocess.run([sys.executable, str(ROOT / "generator" / "simulate.py"), "--out", str(tmp_path / run)], check=True)
    h = []
    for run in ("a", "b"):
        x = hashlib.sha1()
        for f in sorted((tmp_path / run / "events").glob("*.parquet"))[:10]:
            x.update(pd.util.hash_pandas_object(pd.read_parquet(f), index=False).values.tobytes())
        h.append(x.hexdigest())
    assert h[0] == h[1]
    cols = set(pd.read_parquet(sorted((tmp_path / "a" / "events").glob("*.parquet"))[0]).columns)
    assert not cols & {"email", "name", "ip", "device_id", "advertising_id", "phone"}
