# Developer shortcuts. Needs GNU make and uv.
# On Windows, run make from Git Bash (or WSL); GNU make is also available via
# `winget install ezwinports.make` or `scoop install make`.
UV ?= uv

.DEFAULT_GOAL := help
.PHONY: help install install-gui hooks lint format format-check typecheck test cov check run seed run-seed build icon freeze installer clean

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

SEED_DB ?= scratch/seed.sqlite3

seed: ## Create a scratch DB of sample bills at $(SEED_DB) (replacing it)
	$(UV) run python -c "import pathlib; pathlib.Path('$(SEED_DB)').unlink(missing_ok=True)"
	$(UV) run python -m yomil.devtools.seed $(SEED_DB)

run-seed: ## Run the app against the scratch DB (run `make seed` first)
	$(UV) run --extra gui python -m yomil --db $(SEED_DB)

build: ## Build sdist and wheel into dist/
	$(UV) build

icon: ## Redraw the app icon (src/yomil/app/icons/yomil.ico)
	$(UV) run --extra gui python -m yomil.devtools.make_icon

freeze: ## Freeze the app with PyInstaller into dist/pyinstaller/YOMIL, and self-test it
	$(UV) run --extra gui --group package pyinstaller --noconfirm --clean \
		--distpath dist/pyinstaller --workpath build/pyinstaller packaging/yomil.spec
	dist/pyinstaller/YOMIL/yomil --self-test

# Inno Setup's compiler; override if it isn't on PATH, e.g.
# make installer ISCC="/c/Program Files (x86)/Inno Setup 6/ISCC.exe"
ISCC ?= iscc

installer: freeze ## Windows only: build dist/YOMIL-Setup-<version>.exe (needs Inno Setup 6)
	"$(ISCC)" /DAppVersion=$$($(UV) run python -c "import yomil; print(yomil.__version__)") \
		packaging/yomil.iss

clean: ## Remove caches and build output
	$(UV) run python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for n in ('.mypy_cache', '.ruff_cache', '.pytest_cache', '.hypothesis', 'dist', 'build', 'htmlcov') for p in pathlib.Path('.').glob(n)]; pathlib.Path('.coverage').unlink(missing_ok=True)"
