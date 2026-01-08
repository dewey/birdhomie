-- Remove automatic duplicate detection columns
-- Keep: duplicate_of_file_id (needed for manual merge)
-- Remove: overlap_percentage, duplicate_checked_at, frame_hashes_blob
--
-- Note: This uses simple DROP COLUMN (supported in SQLite 3.35.0+, March 2021)
-- Migration 006 used table recreation because it needed to modify the CHECK constraint,
-- but for dropping columns, DROP COLUMN is cleaner and simpler.

ALTER TABLE files DROP COLUMN overlap_percentage;
ALTER TABLE files DROP COLUMN duplicate_checked_at;
ALTER TABLE files DROP COLUMN frame_hashes_blob;
