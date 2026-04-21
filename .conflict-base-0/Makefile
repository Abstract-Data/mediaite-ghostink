.PHONY: help install lint format test coverage clean pipeline scrape extract analyze report

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	uv sync

lint: ## Run linter
	uv run ruff check .

format: ## Format code
	uv run ruff format .

format-check: ## Check formatting without changes
	uv run ruff format --check .

test: ## Run all tests
	uv run pytest tests/ -v

coverage: ## Run tests with coverage
	uv run pytest tests/ -v --cov=src --cov-report=term-missing

clean: ## Clean generated data and caches
	rm -rf data/raw data/features data/analysis data/reports data/pipeline
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

# Pipeline commands
scrape: ## Run scrape stage
	uv run forensics scrape

extract: ## Run feature extraction
	uv run forensics extract

analyze: ## Run analysis stage
	uv run forensics analyze

report: ## Generate report
	uv run forensics report

pipeline: ## Run full pipeline
	uv run forensics all

# Quality gates
check: lint format-check test ## Run all quality checks
