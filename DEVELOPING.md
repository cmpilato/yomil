# YOMIL Development

## Layout

```
src/yomil/
  core/      pure domain logic: models, recurrence, urgency, materialization planning,
             main-list building, validation. No wx, no I/O.
  storage/   SQLite: connection + transactions, versioned SQL migrations
             (PRAGMA user_version), and repository functions (one module per table)
  services/  use cases the UI calls; each write is one transaction plus event_log entries
  app/       wxPython shell: tray icon, main window, entry point
  devtools/  developer-only helpers (seed script); never imported by the app
  paths.py, logging_setup.py
tests/       mirrors src/; everything but app/ runs on any OS, no wxPython needed
```

Rule of thumb: decisions go in `core/`, which takes "today" as a parameter and never
touches the database, filesystem, or wx, so it can be tested exhaustively and ported to
another GUI toolkit if ever needed. `services/` is the thin imperative shell around it:
load rows via `storage/`, ask `core/` what should change, write the result, log it. The
UI talks only to `services/`.

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
Sample data: `make seed` builds `scratch/seed.sqlite3` (bills with history, overdue
payments, and edge cases, relative to today); `make run-seed` runs the app against it.
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
* Connections use `autocommit=True`, so sqlite3 never opens a transaction implicitly.
  Every write goes through `with storage.db.transaction(conn):` (`BEGIN IMMEDIATE` …
  `COMMIT`, or `ROLLBACK` on any exception), and nothing holds a transaction open while
  idle. Tests fail if a service leaves one open.
* Occurrences are materialized lazily and idempotently: every instance from `dtstart`
  through today, plus the following ones up to the first unresolved one. Materialization
  only moves forward (`series.materialized_through`), so schedule edits and reactivation
  never back-fill old dates. A schedule edit regenerates only *future, pending,
  not-hand-moved* payments.
* Every change to a bill or payment writes `event_log` (`detail_json` holds a snapshot
  or `{field: [old, new]}` diffs). Preferences in the `setting` table are not logged.
