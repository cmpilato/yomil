-- App preferences as key/value text, so one file holds everything.
CREATE TABLE setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Set when the user moves a pending occurrence's due date by hand, so that series
-- edits know to leave it alone.
ALTER TABLE occurrence ADD COLUMN due_date_overridden INTEGER NOT NULL DEFAULT 0
    CHECK (due_date_overridden IN (0, 1));

-- Bookkeeping for materialization: occurrences on or before this date are never
-- created again, so schedule edits and reactivation don't back-fill old dates.
ALTER TABLE series ADD COLUMN materialized_through TEXT;
