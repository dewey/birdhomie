-- Add cover image field to visits table

ALTER TABLE visits ADD COLUMN cover_detection_id INTEGER REFERENCES detections(id) ON DELETE SET NULL;

-- Index for efficient queries
CREATE INDEX idx_visits_cover_detection ON visits(cover_detection_id);
