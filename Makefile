.PHONY: install test lint migrate up down sandbox-image

install:
	uv sync --dev

test:
	uv run pytest

lint:
	uv run ruff check src tests

migrate:
	uv run alembic upgrade head

up:
	docker compose -f docker-compose.dev.yml up -d

down:
	docker compose -f docker-compose.dev.yml down

sandbox-image:
	docker build -f Dockerfile.sandbox -t cause-trace-sandbox:latest .
