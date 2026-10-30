-- The paid date becomes a paid date and time: a naive local ISO-8601 timestamp
-- (YYYY-MM-DDTHH:MM:SS), so payments made on the same day sort in the order they
-- were made. Existing payments marked paid on the day they were made take the local
-- time they were marked; the rest (back-dated or corrected) get midnight.
ALTER TABLE occurrence RENAME COLUMN paid_date TO paid_at;

UPDATE occurrence
SET paid_at = CASE
    WHEN date(reconciled_at, 'localtime') = paid_at
        THEN strftime('%Y-%m-%dT%H:%M:%S', reconciled_at, 'localtime')
    ELSE paid_at || 'T00:00:00'
END
WHERE paid_at IS NOT NULL;
