-- Dates are ISO-8601 calendar dates (YYYY-MM-DD); timestamps are UTC ISO-8601.
-- Money is integer cents.

CREATE TABLE series (
    id                    INTEGER PRIMARY KEY,
    payee                 TEXT NOT NULL,
    category              TEXT,
    amount_kind           TEXT NOT NULL DEFAULT 'fixed'
                          CHECK (amount_kind IN ('fixed', 'estimated', 'variable')),
    expected_amount_cents INTEGER,
    rrule                 TEXT NOT NULL,
    dtstart               TEXT NOT NULL,
    until                 TEXT,
    weekend_policy        TEXT NOT NULL DEFAULT 'none'
                          CHECK (weekend_policy IN ('none', 'previous', 'next')),
    lead_days_json        TEXT NOT NULL DEFAULT '[7,3,0]',
    autopay               INTEGER NOT NULL DEFAULT 0 CHECK (autopay IN (0, 1)),
    url                   TEXT,
    notes                 TEXT,
    active                INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE TABLE occurrence (
    id                    INTEGER PRIMARY KEY,
    series_id             INTEGER NOT NULL REFERENCES series (id) ON DELETE RESTRICT,
    nominal_date          TEXT NOT NULL,
    due_date              TEXT NOT NULL,
    expected_amount_cents INTEGER,
    status                TEXT NOT NULL DEFAULT 'upcoming'
                          CHECK (status IN ('upcoming', 'paid', 'skipped')),
    payee_snapshot        TEXT,
    paid_date             TEXT,
    actual_amount_cents   INTEGER,
    note                  TEXT,
    reconciled_at         TEXT,
    UNIQUE (series_id, nominal_date),
    CHECK (status <> 'paid' OR (paid_date IS NOT NULL AND reconciled_at IS NOT NULL))
);

CREATE INDEX idx_occurrence_status_due ON occurrence (status, due_date);

-- Append-only audit trail: every create / edit / reconcile / un-reconcile / skip.
CREATE TABLE event_log (
    id          INTEGER PRIMARY KEY,
    at          TEXT NOT NULL,
    entity      TEXT NOT NULL CHECK (entity IN ('series', 'occurrence')),
    entity_id   INTEGER NOT NULL,
    action      TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_event_log_entity ON event_log (entity, entity_id, at);
