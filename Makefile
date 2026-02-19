.PHONY: help install dev test lint clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Install package
	python3 -m pip install .

dev:  ## Install with dev dependencies
	python3 -m pip install -e ".[dev]"

test:  ## Run tests
	python3 -m pytest tests/ -v --tb=short

lint:  ## Lint with ruff
	python3 -m ruff check src/ tests/

clean:  ## Remove build artefacts
	rm -rf build/ dist/ *.egg-info src/*.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
