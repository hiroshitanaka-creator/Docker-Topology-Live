.PHONY: install scan serve sample test compile demo-up demo-down

install:
	python -m pip install -e .

scan:
	python app.py scan --output topology.json

serve:
	python app.py serve

sample:
	python app.py sample --output topology.json

test:
	python -m unittest discover -s tests

compile:
	python -m compileall app.py src tests

demo-up:
	docker compose -f demo/docker-compose.yml up -d

demo-down:
	docker compose -f demo/docker-compose.yml down -v
