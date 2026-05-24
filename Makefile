.PHONY: sample scan serve doctor compile

sample:
	python app.py sample --output topology.json

scan:
	python app.py scan --output topology.json --sample-on-error

serve:
	python app.py serve --sample

doctor:
	python app.py doctor

compile:
	python -m py_compile app.py
