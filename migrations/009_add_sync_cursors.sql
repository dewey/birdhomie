-- Add sync_cursors table for tracking sync state
-- This enables incremental syncing from last known event time

CREATE TABLE sync_cursors (
    cursor_type TEXT PRIMARY KEY,
    last_event_time TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trigger to update timestamp on change
CREATE TRIGGER update_sync_cursors_timestamp
    AFTER UPDATE ON sync_cursors
    FOR EACH ROW
BEGIN
    UPDATE sync_cursors SET updated_at = CURRENT_TIMESTAMP WHERE cursor_type = NEW.cursor_type;
END;
