.PHONY: up down build logs shell seed migrate ps clean

# ─── Start ────────────────────────────────────────────────────────────────────
up:
	docker compose up -d

up-dev:
	docker compose --profile dev up -d

down:
	docker compose down

build:
	docker compose build --no-cache

restart:
	docker compose restart backend

# ─── Logs ─────────────────────────────────────────────────────────────────────
logs:
	docker compose logs -f

logs-api:
	docker compose logs -f backend

logs-db:
	docker compose logs -f db

# ─── Database ─────────────────────────────────────────────────────────────────
seed:
	docker exec bazarfutures_api python seed.py

shell-db:
	docker exec -it bazarfutures_db psql -U bazarfutures -d bazarfutures

shell-api:
	docker exec -it bazarfutures_api bash

# ─── Scraper (manual trigger) ─────────────────────────────────────────────────
scrape:
	docker exec bazarfutures_api python -c "from scraper import run_price_update; run_price_update()"

settle:
	docker exec bazarfutures_api python -c "from scraper import run_settlement_job; run_settlement_job()"

# ─── Status ───────────────────────────────────────────────────────────────────
ps:
	docker compose ps

# ─── Clean (removes volumes too — CAUTION) ────────────────────────────────────
clean:
	docker compose down -v --remove-orphans
	docker image rm bazarfutures_backend 2>/dev/null || true

# ─── Quick start for first time ───────────────────────────────────────────────
init: build up
	@echo "⏳ Waiting for services..."
	@sleep 8
	@$(MAKE) seed
	@echo ""
	@echo "✅ BazarFutures is running!"
	@echo "   Frontend : http://localhost:3000"
	@echo "   API Docs : http://localhost:8080/docs"
