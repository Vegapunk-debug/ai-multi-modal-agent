.PHONY: install dev server client eval lint clean

PY := python3
VENV := .venv
PIP := $(VENV)/bin/pip

install:
	$(PY) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"
	cd client && npm install

server:
	$(VENV)/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

client:
	cd client && npm run dev

dev:
	@echo "Run 'make server' and 'make client' in two terminals."

eval:
	$(VENV)/bin/pytest evals -v

lint:
	$(VENV)/bin/ruff check server evals

clean:
	rm -rf $(VENV) **/__pycache__ .pytest_cache .ruff_cache
	rm -f *.sqlite *.db
