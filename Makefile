.PHONY: install run lint test check

install:
	pip install -r requirements-dev.txt

run:
	uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

lint:
	ruff check .

test:
	PYTHONPATH=. pytest

check: lint test