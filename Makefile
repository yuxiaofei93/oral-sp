.PHONY: api-install api-test api-lint web-install web-test web-build test

api-install:
	python3 -m venv .venv
	.venv/bin/python -m pip install -c apps/api/constraints.txt -e "./apps/api[dev]"

api-test:
	.venv/bin/python -m pytest apps/api

api-lint:
	.venv/bin/python -m ruff check apps/api

web-install:
	npm --prefix apps/web install

web-test:
	npm --prefix apps/web test

web-build:
	npm --prefix apps/web run build

test: api-test web-test web-build
