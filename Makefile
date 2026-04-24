.PHONY: help install lint format test coverage clean pipeline scrape extract analyze report quarto-build deploy clean-generated all

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	uv sync

lint: ## Run linter (Python sources only; notebooks are executed via Quarto)
	uv run ruff check src tests scripts

format: ## Format code
	uv run ruff format src tests scripts

format-check: ## Check formatting without changes
	uv run ruff format --check src tests scripts

test: ## Run all tests
	uv run pytest tests/ -v

coverage: ## Run tests with coverage (see pyproject.toml addopts / fail_under)
	uv run pytest tests/ -v

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

pipeline: ## Run full pipeline (scrape → extract → analyze → report)
	uv run forensics all

all: pipeline ## Alias for full pipeline including Quarto report

quarto-build: ## Render Quarto book to data/reports
	quarto render --output-dir data/reports

deploy: quarto-build ## Publish HTML book to Cloudflare Pages
	npx wrangler pages deploy data/reports --project-name=ai-writing-forensics

clean-generated: ## Remove extracted features, embeddings, analysis JSON, reports
	rm -rf data/features/*.parquet
	rm -rf data/embeddings/*.npy
	rm -rf data/analysis/*.json
	rm -rf data/reports/*

# Quality gates
check: lint format-check test ## Run all quality checks
