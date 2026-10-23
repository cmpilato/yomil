# Developer shortcuts. Needs GNU make and uv.
# On Windows, run make from Git Bash (or WSL); GNU make is also available via
# `winget install ezwinports.make` or `scoop install make`.
UV ?= uv

.DEFAULT_GOAL := help
.PHONY: help install install-gui hooks lint format format-check typecheck test cov check run build clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-14s %s\n", $$1, $$2}'

install: ## Create .venv and install dev tools (headless core only)
	$(UV) sync --group dev

install-gui: ## Same, plus wxPython (needed to run the GUI)
	$(UV) sync --group dev --extra gui

hooks: ## Install the git pre-commit hook
	$(UV) run pre-commit install

lint: ## Lint with ruff
	$(UV) run ruff check .

format: ## Auto-format with ruff and apply safe lint fixes
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

format-check: ## Verify formatting without changing files
	$(UV) run ruff format --check .

typecheck: ## Type-check with mypy (strict)
	$(UV) run mypy

test: ## Run the test suite
	$(UV) run pytest

cov: ## Run tests with a coverage report
	$(UV) run pytest --cov

check: lint format-check typecheck test ## Everything CI runs

run: ## Run the app (needs the gui extra)
	$(UV) run --extra gui python -m yomil

build: ## Build sdist and wheel into dist/
	$(UV) build

clean: ## Remove caches and build output
	$(UV) run python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for n in ('.mypy_cache', '.ruff_cache', '.pytest_cache', '.hypothesis', 'dist', 'build', 'htmlcov') for p in pathlib.Path('.').glob(n)]; pathlib.Path('.coverage').unlink(missing_ok=True)"
