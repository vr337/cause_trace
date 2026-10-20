.PHONY: install test test-mysql lint migrate migrate-reset seed up down api sandbox sandbox-image api-image api-container test-pdf

install:
	uv sync --dev

test:
	uv run pytest

test-mysql:
	CAUSE_TEST_MYSQL=1 \
	CAUSE_DATABASE_URL="mysql+pymysql://cause:causepass@127.0.0.1:3306/cause_it?charset=utf8mb4" \
	uv run pytest tests/test_integration_mysql.py

lint:
	uv run ruff check src tests

migrate:
	uv run alembic upgrade head

# 表被手工 drop 过时 alembic_version 仍在，upgrade 会以为已是最新而跳过；
# 这个目标先清版本记录再重建，只用于本地开发库，别对生产跑。
migrate-reset:
	docker exec cause-mysql mysql -ucause -pcausepass cause -e "DROP TABLE IF EXISTS alembic_version;"
	uv run alembic upgrade head
	docker exec -i cause-mysql mysql -ucause -pcausepass cause < scripts/seed_demo.sql

seed:
	docker exec -i cause-mysql mysql -ucause -pcausepass cause < scripts/seed_demo.sql

up:
	docker compose -f docker-compose.dev.yml up -d

down:
	docker compose -f docker-compose.dev.yml down

api:
	uv run uvicorn cause_trace.main:app --port 7300 --reload

sandbox:
	uv run uvicorn cause_trace.sandbox.service:app --port 7400

sandbox-image:
	docker build -f Dockerfile.sandbox -t cause-trace-sandbox:latest .

# PDF 渲染依赖 WeasyPrint 的 Pango/Cairo，统一在容器里做，本地不装 GTK
api-image:
	docker build -f Dockerfile -t cause-trace-api:test .

api-container:
	docker compose -f docker-compose.dev.yml --profile api up -d api

test-pdf:
	bash scripts/e2e_pdf_container.sh
