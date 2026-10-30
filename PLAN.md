# YOMIL Implementation Plan

Status: **draft for iteration.** Edit freely; decisions marked _(open)_ are not settled.

This plan turns the original UI sketch ("YOMIL - Bill Payment Tracker for Your Old
Mother-in-Law") into phased work on top of the existing scaffold (see
[DEVELOPING.md](./DEVELOPING.md) for layout and design rules).

## Who it's for

One elderly, non-technical user on her own Windows PC. She does everything herself:
sets up her bills, reconciles them, and checks history. That drives these
requirements throughout:

* Large, configurable fonts. Status is never shown by color alone (text and/or icon too).
* Everything works from the keyboard. Every double-click action also has a visible
  button and responds to Enter.
* Forgiving: confirm destructive actions, warn on unsaved changes, and make every
  mistake reversible (un-reconcile, edit history). Every change goes to the audit log.
* Installs like a normal Windows program. She never sees Python.

## Development constraints

The designer's familiarity with wxPython is non-zero, but quite stale and was never
developed according to any best-practices in the first place.  This project is intended
both to serve the user's needs _and_ the goal of (re-)educating the developer.  Along the
way, if there are multiple "best practices" to choose from, the developer should be
advised and prompted for a decision.

## Vocabulary

The sketch's terms, mapped to the existing domain model (`core/models.py`):

| Sketch says                         | Model                            | UI label (proposed) |
|-------------------------------------|----------------------------------|---------------------|
| scheduled payment / event           | `Series` (template; may be one-time) | Bill            |
| instance / transaction              | `Occurrence`                     | Payment             |
| reconcile                           | `Occurrence.status = paid`       | Mark Paid           |
| (new) skip                          | `Occurrence.status = skipped`    | Skip                |
| transaction history                 | paid + skipped `Occurrence`s     | Payment History     |
| (audit) log                         | `event_log` (append-only)        | Change history      |

A "singleton" bill is a `Series` whose rule is `COUNT=1`, so one code path covers both.

## Sketch review: gaps found and how they were resolved

| # | Gap or ambiguity in the sketch | Resolution |
|---|---|---|
| 1 | No way to create, edit, or retire bills | First-class **Manage Bills** dialog (Phase 4) |
| 2 | "Sorted by nearest instance" for recurring bills | **One row per bill**: its oldest unresolved payment |
| 3 | Editor edits "date": which date? | Editable: **due date, paid date, actual amount, note** |
| 4 | No way to fix a mistaken reconcile | **Un-reconcile** and **edit reconciled entry**, both logged |
| 5 | No way to dismiss a bill that needn't be paid | **Skip** an instance |
| 6 | "Event Viewer Dialog" undefined | **Read-only details plus change history**, with buttons for corrections |
| 7 | `UPCOMING_THRESHOLD` vs existing per-bill `lead_days` | **One global threshold** for colors; `lead_days` only times notifications |
| 8 | Tray, toasts, run-at-login (README) missing from sketch | Kept, as a **later phase** |
| 9 | Data safety not mentioned | Live-safe for **Duplicati** backups, plus **manual export** |
| 10 | Deployment not mentioned | **Frozen .exe + installer** |
| 11 | Double-click is the only way to act | Also Enter and visible buttons (accessibility) |
| 12 | "Exit" vs. close-to-tray | Window close hides to tray; **Exit** really quits |
| 13 | Typo: "mark the event as reconciles" | Reconcile = save changes, then mark paid |

## Cross-cutting decisions

* **Today** is injected everywhere in `core/` (existing rule). The app refreshes at
  local midnight and when the window is shown, so an always-running tray app never
  shows yesterday's colors.
* **Materialization.** Occurrence rows are created lazily and idempotently (the
  `UNIQUE(series_id, nominal_date)` constraint makes inserts safe to repeat). For each
  active series, rows exist from `dtstart` through today, plus each following instance
  up to and including the first unresolved one (normally just the next one after today;
  paying ahead brings up the one after that). `dtstart` *is* the first due date, so
  creating a bill never back-fills a flood of overdue payments. Materialization only
  moves forward (`series.materialized_through`), so schedule edits and reactivating a
  retired bill don't back-fill either.
* **Transaction discipline (backup safety).** In rollback-journal mode the DB file is
  consistent on disk whenever no write transaction is open. Every write is one short
  explicit transaction. No transaction is ever left open while idle; tests assert
  `conn.in_transaction is False` after every service call. This is what makes it safe
  for Duplicati to copy the file while the app runs (see Phase 7 for the extra guarantee).
* **Settings** live in a `setting` key/value table in the same DB, so one file holds
  everything (backups and debug transfers stay simple).
* **Money** is integer cents, shown with the user's locale currency format (or USD if that can't be determined).

## Phases

Each phase ends with `make check` green and a short manual test on Windows (for any
phase touching `app/`).

### Phase 1: Core services (headless) — done

Goal: every operation the UI needs, fully tested without wx.

* Migration `0002`: `setting` table; `occurrence.due_date_overridden` flag (so series
  edits know which pending payments the user moved by hand).
* `storage/` repository functions: series CRUD; occurrence queries; settings get/set.
* `services/` functions, each one transaction and each writing `event_log`:
  * `materialize(conn, today)`
  * `main_list(conn, today) -> list[BillRow]`: one row per active bill (its oldest
    `upcoming` occurrence), plus a count of further overdue occurrences for that bill.
  * `update_pending(occ, due_date, note)`
  * `reconcile(occ, paid_date, actual_amount_cents, note)`: snapshots payee
  * `skip(occ, note)`, `unreconcile(occ)`, `edit_reconciled(occ, paid_date, amount, note)`
  * `history(conn) -> list[...]`: paid + skipped, by paid/skip date descending
* `classify(due_date, today, threshold) -> Urgency` (`OVERDUE`, `DUE_SOON`, `LATER`).
* Series edits: regenerate *future, pending, not-overridden* occurrences. Leave overdue,
  overridden, and resolved ones alone.
* Dev seed script (`make seed`) that fills a scratch DB with realistic bills, including
  overdue ones, month-end edge cases, and a one-time bill.

Exit: property tests for materialization idempotency and series-edit regeneration;
tests for every service, including the audit-log entries and the no-open-transaction
invariant.

Decisions made while implementing:
* Services live in a new `services/` layer (not `core/`), keeping `core/` free of I/O.
* Connections use `autocommit=True` with explicit `BEGIN IMMEDIATE` transactions.
* Added `series.materialized_through` (see Materialization above): a property test
  found that without it, a schedule edit back-filled dates the old schedule never had.
* Skipped payments also snapshot the payee; history sorts skipped ones by due date.
* `edit_reconciled` applies to paid payments only; `unreconcile` also un-skips.
* Setting changes are not written to `event_log` (its `entity` CHECK allows only
  series and occurrence).

### Phase 2: Main frame — built; Windows manual test pending

* Report-style list. Columns: Due, Bill, Amount, Status ("Overdue 3 days", "Due
  tomorrow", "In 12 days"), Note. Sorted by due date, then bill name.
* Row styling by `Urgency`: overdue gets a strong error style plus a "⚠ OVERDUE" status
  text; due-soon gets a warning style; later is plain. Colors are picked for
  color-blind contrast.
* A bill with more than one overdue payment shows "(+N more overdue)". Resolving the
  oldest brings up the next.
* Item activation (double-click or Enter) opens the Event Editor. A visible **Open…**
  button does the same. A **Mark Paid** button pays the selected bill today at its
  expected amount, after a confirm.
* Menus: **File** › Export… (Phase 7), Exit · **Bills** › Manage Bills… (Phase 4),
  Payment History… (Phase 5) · **Tools** › Preferences… (Phase 6).
* Empty state that points to Manage Bills. Refresh at midnight (wx.Timer) and on show.
* Applies font preferences (defaults until Phase 6).

Exit: run against the seed DB on Windows at normal and large font sizes.

Decisions made while implementing:
* The list is a **virtual `wx.ListCtrl`** (native ListView on Windows), not
  `DataViewListCtrl`. The rows live in one Python list; the control asks for text and
  styling per visible row.
* All wording (dates, money, status, the status-bar summary) is in `core/formatting.py`
  and unit-tested; `app/` adds only styling.
* Dates read "Tue Mar 3, 2026". Estimated amounts read "About $120.00"; variable bills
  without an amount read "Varies".
* Money uses the locale's currency format, read once at startup *before* `wx.App`
  exists, then the process locale is restored (wx asserts on Windows if Python changes
  the C runtime locale under it). USD if the locale has none.
* **Mark Paid** is disabled when there's no expected amount; for estimated and variable
  bills the confirm says it's the expected amount and points to Open….
* After Mark Paid, the selection stays at the same row position (she works down the
  list). Other refreshes keep the same bill selected.
* Refresh also happens on window activation if the date changed (catches a missed
  midnight timer after sleep).
* A status bar shows "2 bills overdue, 1 due soon" (one more non-color cue).
* The window widens (up to the screen) when a larger font needs it.
* `list_font_size` setting added now (no UI until Phase 6). Menu items for later phases
  are present but disabled; **Open…** shows a placeholder until Phase 3.

### Phase 3: Event Editor (pending payment) — built; Windows manual test pending

* Read-only header: bill name, nominal due date, expected amount, bill notes, and the
  bill's URL as a clickable link (for paying online).
* Fields: due date, paid date (default today), actual amount (default expected; required
  for variable-amount bills), note.
* Buttons: **Close**, **Save** (persists due date and note), **Mark Paid** (saves, then
  reconciles), **Skip** (confirms).
* Closing with unsaved edits asks first. Invalid amounts or dates are flagged inline, not
  in modal error boxes.

Milestone: **usable core loop**. Bills from the seed script can be worked down.

Decisions made while implementing:
* Dates use the native `wx.adv.DatePickerCtrl` (always a valid date, so only the amount
  needs checking).
* Field rules live in a pure form check (`core/payment_form.py`, plus `parse_money` in
  `core/formatting.py`), run on every keystroke; not `wx.Validator`s. Errors are
  prefixed "⚠" and block **Mark Paid**; hints (blank amount, future paid date) don't.
* Amount entry tolerates "$", spaces, and thousands separators; anything else (three
  decimals, letters, a minus) is flagged rather than guessed at.
* Future paid dates are allowed, with an inline "Is that right?" note.
* **Save** keeps due date and note only. Closing asks to Save / Don't Save / Keep
  Editing when those changed, and separately warns if a paid date or amount was entered
  but not marked paid.
* `reconcile` and `skip` take an optional `due_date`, so Mark Paid and Skip save a moved
  due date in the same transaction (one audit entry), not as a separate Save.
* Save, Mark Paid, and Skip each close the dialog. Enter in the amount field marks it
  paid. After paying or skipping, the main list selects whatever moved into that row.
* The header shows the *scheduled* date (nominal after weekend policy: what an
  un-overridden due date would be) and, if any, how many more payments are overdue.

### Phase 4: Manage Bills — built; Windows manual test pending

* List of all bills (active first; retired shown greyed). Buttons: Add, Edit, Retire /
  Reactivate, Delete. Delete is allowed only if the bill has no paid history (matches
  `ON DELETE RESTRICT`); otherwise she's offered Retire.
* Bill editor with a friendly schedule picker. No raw RRULEs:
  One time · Every N weeks on <weekday> · Every N months on day D (uses
  `monthly_on_day`) · Yearly on <date>. Plus first due date, optional end date, weekend
  policy, amount kind and expected amount, autopay, URL, notes, category.
* Live preview: "Next 5 due dates: …" so she can check the schedule before saving.
* `lead_days` is hidden until Phase 9 ships notifications.

Decisions made while implementing:
* Hand-written sizers again (wxFormBuilder/XRC considered; strict typing and the
  conditional layout won out).
* **The schedule is "how often"; the day comes from the first due date**
  (`core/schedule.py`). Repeats: One time only / Weekly / Monthly / Yearly, with "every
  N". The weekday, day of month, or month and day are read off the first due date and
  described in words ("Every 3 months on the 3rd"), so the first due date is always a
  real occurrence. dateutil silently drops a `dtstart` that doesn't match its rule.
* Rules are parsed back only if the picker would write *exactly* that rule; anything
  else is shown as "Custom (set up outside YOMIL)" and kept untouched unless she picks
  a new schedule. So opening and saving a bill never rewrites its rule (tested).
* Month-end: a first due date on the 29th–31st means "or the last day of shorter
  months". A monthly bill whose first due date is a *clamped* month-end (e.g. "the
  31st", first due April 30) keeps its day as `Schedule.month_day` until the first due
  date is changed. Feb 29 yearly bills fall on Feb 28 in common years.
* Field rules live in `core/bill_form.py` (`check_bill`, `schedule_summary`), shared
  `FieldMessage` in `core/forms.py`. Messages appear once a field is touched, or on all
  fields after a Save attempt, which also focuses the first bad field.
* The preview lists the next 5 due dates (after weekend adjustment), warns how many
  payments a *new* bill with a past first due date will create as overdue, and, on an
  edit, notes that upcoming un-moved payments will follow the new schedule.
* Web addresses: "example.com" becomes "https://example.com"; only http(s) is allowed.
  A duplicate bill name is a hint, not an error.
* Manage Bills uses a plain (non-virtual) `ListCtrl`, rebuilt after each change.
  Retired bills are greyed *and* say "Retired". Delete key deletes. Retire needs no
  confirm (Reactivate undoes it); Delete confirms, and for a bill with history offers
  Retire instead.
* Controls inside a `StaticBoxSizer` are children of its `StaticBox` (wx 3.x rule).
* The main window's empty state now has a **Manage Bills…** button.

### Phase 5: Payment History and Event Viewer — built; Windows manual test pending

* History list: date, bill (snapshotted name), amount, Paid/Skipped, note. Most recent
  first. Activation opens the Event Viewer.
* Event Viewer: read-only details of one payment. Buttons: **Edit…** (paid date, amount,
  note), **Un-reconcile** (confirms, returns the payment to the main list), **Close**.

Decisions made while implementing:
* Payment History is the "check register": the one place to browse past payments. No
  filtering or search yet; add it if she asks.
* **The Event Viewer does not show `event_log`.** The audit trail keeps recording every
  change, but it's for debugging and deep auditing, not for her. (Export could expose it
  later.)
* Plain words instead of "un-reconcile": **Mark Unpaid…** for paid payments, **Undo
  Skip…** for skipped ones (which have no Edit…). The confirmation warns when the bill
  is retired, since the payment then won't reappear on the main list.
* Edit… opens a separate small dialog (`app/payment_editor.py`), reusing the Event
  Editor's field checks (`core/payment_form.py`), so looking can't change anything by
  accident. In the viewer, Close is the default and has the focus.
* Skipped rows are greyed *and* say "Skipped" (amount "—"). They're listed under their
  due date; paid ones under their paid date. The viewer shows "Expected amount" only
  when it differs from what was paid, and "Bill now called" if the bill was renamed.
* Display rules are pure, in `core/history.py`. The editors' field-message helpers moved
  to `app/fields.py`; the report lists' font and column sizing to `app/lists.py`.

### Phase 6: Preferences — built; Windows manual test pending

* Font family and size for the lists, with a live preview. _(open: scale the whole app,
  not just the lists? Probably better for her.)_
* "Upcoming soon" threshold in days (default 7).
* Stored in the `setting` table; applied right away without a restart.

Decisions made while implementing:
* **One text size for the whole app**, not just the lists: lists, labels, fields,
  buttons, dialogs. Native menus, message boxes, and date-picker popups follow Windows'
  own text size (Settings › Accessibility › Text size), which is worth raising on her PC
  too. The setting is now `font_size` (was `list_font_size`).
* **Size only, as a point-size spinner (8–36)**, no font family: the Windows UI font
  stays. "Use Windows Size" resets it; saving the Windows size stores nothing, so YOMIL
  follows Windows if that changes later.
* How it's applied (`app/fonts.py`): wx hands an explicitly set font to child windows as
  they're created, but not to dialogs and not to existing children. So every dialog
  copies its parent's font first thing (`inherit_font`), and the main window re-fonts
  itself recursively when the setting changes. The list dialogs' starting size scales
  with the font; dialogs never grow past the screen.
* The live preview is a real `BillListCtrl` with made-up bills (`core/preferences.py`)
  plus a sample text field; changing "due soon" recolors it. Nothing applies until
  **Save**; then the main window refreshes. Cancel with changes asks Save / Don't Save /
  Keep Editing. Both settings are saved in one transaction (`save_preferences`).

### Phase 7: Data safety and export — built; Windows manual test pending

* **Live-backup safety:** on top of Phase 1's transaction discipline, after each
  committed change write a consistent snapshot with SQLite's online backup API
  (`Connection.backup`) to `<data dir>/snapshot/yomil.sqlite3` (write to a temp file,
  then `os.replace`). Even if Duplicati copies the main file mid-write, the snapshot is
  always intact. Document the data dir, and recommend Duplicati's
  `--snapshot-policy=auto` (VSS).
* **File › Export…:** (a) a full database copy via the backup API, which opens directly
  with `yomil --db <file>` for debugging on another machine; (b) a CSV of payment
  history she can print or hand to someone.
* Startup integrity check (`PRAGMA quick_check`); if it fails, a clear message
  pointing to the snapshot.

Decisions made while implementing:
* **Snapshots are driven by SQLite's change counter**, not hooks: a 2-second `wx.Timer`
  (`app/safety.py`) snapshots when `conn.total_changes` has moved, plus once at startup
  and at exit. Nothing else in the app has to remember to call it. A failed write (e.g.
  the file is held open) is logged once and retried on the next tick.
* The snapshot lives beside whichever database is open (`<db folder>/snapshot/`), so
  `--db` debugging sessions never overwrite her snapshot.
* **No full-database export:** SQLite files are portable, and the snapshot is already a
  consistent copy, so File has just **Export Payment History…** (CSV: UTF-8 with BOM for
  Excel, ISO dates, plain `1234.56` amounts, skipped payments included, defaulting to
  her Documents folder with a dated name).
* **Damaged at startup:** if the snapshot passes its own check, she's offered
  **Restore Safety Copy** / **Quit**, with the copy's date and time. Restoring renames the
  damaged file (and its `-journal`, which SQLite would otherwise replay into the
  restored file) to `yomil-damaged-<timestamp>.sqlite3`. With no usable snapshot, she's
  told not to use YOMIL until someone looks at it, and it quits.
* The integrity check opens the file read-write on purpose: after a crash mid-commit,
  rolling back the leftover journal is normal recovery, not damage (tested).
* Data folder, backups, and debugging are documented in DEVELOPING.md.

Milestone: **safe to hold real data.**

### Phase 8: Packaging and installer

* Freeze with PyInstaller (windowed, one-folder). Real app icon to replace the
  drawn placeholder.
* Installer (Inno Setup or similar): Start Menu and optional desktop shortcut,
  uninstaller that **never** deletes the data dir, and upgrade-in-place.
* CI job that builds the installer on `windows-latest` and uploads it as an artifact.
* Version shown in an About box (Help menu).

Milestone: **first deployment to her PC** (Phases 1–8).

### Phase 9: Notifications and run-at-login

* Windows toast notifications at each bill's `lead_days` before its due date, and for
  overdue payments. Clicking one opens the app on that payment. Fired at most once per
  (occurrence, lead day): remembered in `setting` or a small table.
* Tray icon tooltip shows "2 overdue, 1 due soon". Optional badge on the icon.
* Run-at-login option (installer checkbox plus a Preferences toggle), launching with
  `--minimized`.
* Expose `lead_days` in the bill editor.

## Open questions

1. **Autopay bills:** show them, but reconcile automatically on the due date? Or still
   require her to confirm? Or hide them?
2. ~~**Save vs. Mark Paid:** should "Save" also keep a half-entered paid date and amount
   as a draft, or only due date and note (current proposal)?~~ Due date and note only
   (Phase 3).
3. ~~**Future paid dates:** allow them (e.g., a check mailed or bill-pay scheduled for
   later) or warn?~~ Allowed, with an inline note (Phase 3).
4. ~~**Main-list actions:** add a direct "Mark Paid (today, expected amount)" button for
   the common case?~~ Yes, with a confirm (Phase 2).
5. ~~**Font scope:** lists only (as sketched) or the whole UI?~~ Whole UI (Phase 6).
6. **Currency/locale:** USD only?
7. ~~**History scope:** include skipped payments (proposed yes)? Any filtering?~~ Skipped
   payments included (greyed, labelled); no filtering yet (Phase 5).
8. **Series edits:** is "regenerate future, pending, not-overridden payments" the right rule?
9. **Overdue display:** with one row per bill, is "(+N more overdue)" clear enough, or
   should multiple overdue payments for one bill get separate rows?
