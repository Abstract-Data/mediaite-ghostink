# Peer reviewers use `make peer-setup` (sync dev+tui, validate, then `forensics peer-setup` hints).
.PHONY: help install install-reviewer install-baseline install-probability install-all-extras \
	peer-verify peer-verify-network peer-setup peer-hints lint format test coverage clean \
	pipeline scrape extract analyze report quarto-build deploy clean-generated all

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies (minimal; use install-reviewer for dev+tui)
	uv sync

install-reviewer: ## Python deps for review: dev + tui (no torch / baseline extras)
	uv sync --extra dev --extra tui

install-baseline: ## Reviewer + Phase 10 baseline (pydantic-ai); still no torch
	uv sync --extra dev --extra tui --extra baseline

install-probability: ## Reviewer + Phase 9 probability (large torch/transformers download)
	uv sync --extra dev --extra tui --extra probability

install-all-extras: ## All optional extras (large download; full optional tracks)
	uv sync --extra dev --extra tui --extra baseline --extra probability

peer-verify: ## Run forensics validate (includes preflight)
	uv run forensics validate

peer-verify-network: ## Validate plus WordPress/Ollama endpoint probes (warnings only)
	uv run forensics validate --check-endpoints

peer-hints: ## Print copy-paste setup commands (uv, Ollama pulls from config, etc.)
	uv run forensics peer-setup

peer-setup: install-reviewer peer-verify ## One-shot peer bootstrap: sync, validate, setup hints
	uv run forensics peer-setup

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
