-- Reminder notifications already shown, so each is shown once. ``reminder_key`` is a
-- lead day (days before the due date) or, for overdue payments, minus the days overdue.
CREATE TABLE reminder_sent (
    occurrence_id INTEGER NOT NULL REFERENCES occurrence (id) ON DELETE CASCADE,
    reminder_key  INTEGER NOT NULL,
    sent_at       TEXT NOT NULL,
    PRIMARY KEY (occurrence_id, reminder_key)
);
