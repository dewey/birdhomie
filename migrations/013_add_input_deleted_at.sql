-- Track when input files are cleaned up by the retention policy
ALTER TABLE files ADD COLUMN input_deleted_at TIMESTAMP;
