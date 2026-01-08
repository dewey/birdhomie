-- Add focus point coordinates to detections table

ALTER TABLE detections ADD COLUMN focus_x INTEGER;
ALTER TABLE detections ADD COLUMN focus_y INTEGER;
ALTER TABLE detections ADD COLUMN focus_method TEXT DEFAULT 'heuristic';
ALTER TABLE detections ADD COLUMN focus_computed_at TIMESTAMP;

-- Create index for efficient queries
CREATE INDEX idx_detections_focus ON detections(focus_x, focus_y)
WHERE focus_x IS NOT NULL AND focus_y IS NOT NULL;
