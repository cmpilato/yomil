# YOMIL Development

## Layout

```
src/yomil/
  core/      headless domain logic (models, recurrence). No wx, no I/O.
  storage/   SQLite connection + versioned SQL migrations (PRAGMA user_version)
  app/       wxPython shell: tray icon, main window, entry point
  paths.py, logging_setup.py
tests/       mirrors src/; core + storage run on any OS, no wxPython needed
```

Rule of thumb: logic goes in `core/`, which takes "today" as a parameter and never
touches the filesystem or wx, so it can be tested exhaustively and ported to another
GUI toolkit if ever needed.

## Development

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```
uv sync --group dev              # headless core: works on any OS
uv sync --group dev --extra gui  # adds wxPython (needed to run the GUI)

uv run pytest                    # tests
uv run ruff check . && uv run ruff format --check .
uv run mypy                      # strict
uv run pre-commit install        # run the checks on every commit
```

A `Makefile` wraps the common commands: run `make help` to list them, and `make check`
to run everything CI runs (lint, format check, type-check, tests). On Windows, run make
from Git Bash or WSL.

Run the app: `make run`, or `uv run --extra gui python -m yomil`.
Useful flags: `--minimized` (start hidden in the tray), `--no-tray`, `--db PATH`.

Target platform is Windows; development happens on Linux. The tray icon, toasts, and
run-at-login are Windows features and are verified on Windows. On Linux (stock GNOME has
no tray) the app falls back to a plain window: closing it quits. Use `--no-tray` to force
that mode anywhere.

Logs go to the per-user log directory (the app has no console when launched via the
windowed entry point, so `print()` output is not visible).

## Design decisions

* Money is integer cents. Dates are naive local calendar dates.
* Series (templates) generate occurrences; reconciled occurrences snapshot the payee
  so later edits never rewrite history. `event_log` is append-only.
* RRULE semantics via python-dateutil; `monthly_on_day(31)` clamps to month end
  rather than skipping short months. Weekend adjustment applies to the displayed due
  date only, never to the recurrence anchor.
* SQLite in default rollback-journal mode so the DB stays one file, safe to back up or
  put in a synced folder.
