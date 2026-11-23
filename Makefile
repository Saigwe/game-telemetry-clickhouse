PY ?= python

.PHONY: all ci data pipeline full test dashboards benchmark serve clean

all: data pipeline dashboards
ci: data pipeline test dashboards

data:
	$(PY) generator/simulate.py --out data/raw

# Day-by-day incremental run with a three-day watermark, an idempotency check, then a full backfill.
pipeline:
	$(PY) pipeline/run.py --mode incremental --check-idempotent
	$(PY) pipeline/run.py --mode full
	$(PY) pipeline/benchmark.py --out analysis/benchmark.json

test:
	$(PY) -m pytest -q

dashboards:
	$(PY) dashboards/export.py --out dashboards/site/data.json
	$(PY) dashboards/build.py
	$(PY) analysis/incident_review.py --out analysis/incident_review.md

serve:
	$(PY) -m http.server 8000 --directory dashboards/site

clean:
	rm -rf data/raw dashboards/site/data.json dashboards/site/data.js dashboards/site/*.html
