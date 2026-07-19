.PHONY: help local-config local-infra migrate local-up local-down local-reset logs \
        test test-unit test-integration smoke lint typecheck security fmt

# ── Help ──────────────────────────────────────────────────────────────────────

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Environment ───────────────────────────────────────────────────────────────

local-config: ## Validate docker-compose configuration against .env
	docker compose --env-file .env config

# ── Infrastructure ────────────────────────────────────────────────────────────

local-infra: ## Start only PostgreSQL, NATS and Valkey
	docker compose up -d postgres nats valkey
	@echo "Waiting for infrastructure to become healthy..."
	@./scripts/wait-healthy.sh postgres nats valkey

migrate: ## Run Alembic migrations (one-shot container)
	docker compose run --rm migrate

# ── Full Stack ────────────────────────────────────────────────────────────────

local-up: ## Start everything: infra + migrations + all services
	./scripts/local-up.sh

local-down: ## Stop and remove containers (keeps volumes)
	docker compose down

local-reset: ## Full reset: down, remove volumes, rebuild images, start
	docker compose down -v --remove-orphans
	docker compose build --no-cache
	./scripts/local-up.sh

logs: ## Follow logs for all services
	docker compose logs -f

logs-api: ## Follow API logs only
	docker compose logs -f api

logs-gateway: ## Follow gateway logs only
	docker compose logs -f gateway

logs-workers: ## Follow all worker logs
	docker compose logs -f outbox-publisher lifecycle-consumer scheduler

# ── Testing ───────────────────────────────────────────────────────────────────

test: test-unit test-integration ## Run all tests

test-unit: ## Run unit tests (no external services required)
	pytest tests/unit -q --tb=short

test-integration: ## Run real-service integration tests (requires Docker)
	pytest tests/integration_real -q --tb=short

smoke: ## Run smoke tests against running local stack
	./scripts/smoke-local.sh

# ── Code Quality ──────────────────────────────────────────────────────────────

lint: ## Run ruff linter
	ruff check app/ tests/

fmt: ## Run ruff formatter
	ruff format app/ tests/

typecheck: ## Run mypy type checker
	mypy app/

security: ## Run Trivy security scan on the API image
	docker build -t veyaan-api-scan:local .
	trivy image --exit-code 1 --severity HIGH,CRITICAL veyaan-api-scan:local
