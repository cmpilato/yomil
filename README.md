# YOMIL - Your Obligations, Monitored, Informed, Logged

A small Windows tray app for recurring bill reminders: scheduled bills with
recurrence, notifications for upcoming due dates, manual reconciliation with a
free-form note ("Paid online", "Paid with check #3465"), and a permanent log of
every reconciliation. It is deliberately *not* an account tracker.

**Status:** scaffold. The core recurrence logic, SQLite schema/migrations, logging,
and a tray-icon shell exist; the real UI, notifications, and reconciliation
workflow are still to come.

For developer information, see [DEVELOPING.md](./DEVELOPING.md).