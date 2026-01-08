-- Fix missing duplicate detection columns from migration 006

-- Add missing columns
ALTER TABLE files ADD COLUMN overlap_percentage REAL;
ALTER TABLE files ADD COLUMN duplicate_checked_at TIMESTAMP;
ALTER TABLE files ADD COLUMN frame_hashes_blob BLOB;

-- Create index for efficient duplicate detection queries
CREATE INDEX IF NOT EXISTS idx_files_duplicate_checked ON files(duplicate_checked_at);
CREATE INDEX IF NOT EXISTS idx_files_duplicate_of ON files(duplicate_of_file_id);
