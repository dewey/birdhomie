-- Add soft delete support to visits table

ALTER TABLE visits ADD COLUMN deleted_at TIMESTAMP;

-- Create index for filtering out soft-deleted visits
CREATE INDEX idx_visits_deleted_at ON visits(deleted_at);
