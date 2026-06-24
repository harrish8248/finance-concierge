# Makefile for finance-concierge agent project

.PHONY: install playground run test lint clean

install:
	uv sync --link-mode=copy

playground:
	uv run adk web app --host 127.0.0.1 --port 18081 --reload_agents

run:
	uv run adk run app --host 127.0.0.1 --port 8090

test:
	uv run pytest tests/unit

lint:
	uv run ruff check app

clean:
	rm -rf .venv __pycache__ app/__pycache__ tests/__pycache__
