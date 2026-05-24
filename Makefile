.PHONY: install test compile sample scan serve serve-live doctor lint clean

install:
	pip install -e .

## ── Validation ──────────────────────────────────────────────
compile:
	PYTHONPATH=src python -m compileall app.py src tests

test:
	PYTHONPATH=src python -m unittest discover -s tests -v

## ── Run modes ───────────────────────────────────────────────
sample:
	PYTHONPATH=src python app.py sample --output topology.json

scan:
	PYTHONPATH=src python app.py scan --output topology.json --sample-on-error

serve:
	PYTHONPATH=src python app.py serve --sample

serve-live:
	PYTHONPATH=src python app.py serve

doctor:
	PYTHONPATH=src python app.py doctor

## ── Housekeeping ────────────────────────────────────────────
clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info \
	       __pycache__ src/**/__pycache__ tests/__pycache__ \
	       topology.json .pytest_cache
