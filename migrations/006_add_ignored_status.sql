-- Add 'ignored' status for duplicate files

-- We need to recreate the table to modify the CHECK constraint
-- SQLite doesn't support ALTER COLUMN directly

-- Step 1: Create new table with updated CHECK constraint
CREATE TABLE files_new (
    id INTEGER PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT NOT NULL,
    source_event_id TEXT,
    event_start TIMESTAMP NOT NULL,
    event_end TIMESTAMP,
    duration_seconds REAL,
    output_dir TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'success', 'failed', 'ignored')),
    error_message TEXT,
    duplicate_of_file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
    overlap_percentage REAL,
    duplicate_checked_at TIMESTAMP,
    frame_hashes_blob BLOB
);

-- Step 2: Copy existing data
INSERT INTO files_new SELECT
    id, file_path, file_hash, source_event_id, event_start, event_end,
    duration_seconds, output_dir, created_at, updated_at, processed_at,
    status, error_message,
    NULL as duplicate_of_file_id,
    NULL as overlap_percentage,
    NULL as duplicate_checked_at,
    NULL as frame_hashes_blob
FROM files;

-- Step 3: Drop old table
DROP TABLE files;

-- Step 4: Rename new table
ALTER TABLE files_new RENAME TO files;

-- Step 5: Recreate indices
CREATE INDEX idx_files_status ON files(status);
CREATE INDEX idx_files_event_start ON files(event_start);
CREATE INDEX idx_files_hash ON files(file_hash);
CREATE INDEX idx_files_duplicate_of ON files(duplicate_of_file_id);
CREATE INDEX idx_files_duplicate_checked ON files(duplicate_checked_at);

-- Step 6: Recreate triggers
CREATE TRIGGER update_files_timestamp
    AFTER UPDATE ON files
    FOR EACH ROW
BEGIN
    UPDATE files SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
