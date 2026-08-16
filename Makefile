.DEFAULT_GOAL := help
.PHONY: help install lint typecheck test test-integration cov run migrate seed up down fmt

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install the package with dev extras
	pip install -e ".[dev]"

fmt: ## Auto-format and fix lint issues
	ruff format src tests
	ruff check --fix src tests

lint: ## Run the linter
	ruff check src tests

typecheck: ## Run static type checks
	mypy src

test: ## Run unit and API tests
	pytest -m "not integration"

test-integration: ## Run integration tests (requires Docker)
	pytest -m integration

cov: ## Run tests with coverage
	pytest -m "not integration" --cov --cov-report=term-missing

run: ## Run the API locally
	cascade

migrate: ## Apply database migrations
	alembic upgrade head

seed: ## Insert demo data
	python scripts/seed.py

up: ## Start the local stack
	docker compose up --build -d

down: ## Stop the local stack
	docker compose down -v
