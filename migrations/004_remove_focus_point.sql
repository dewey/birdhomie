-- Remove focus point columns (replaced by face bounding boxes)

DROP INDEX IF EXISTS idx_detections_focus;

ALTER TABLE detections DROP COLUMN focus_x;
ALTER TABLE detections DROP COLUMN focus_y;
ALTER TABLE detections DROP COLUMN focus_method;
ALTER TABLE detections DROP COLUMN focus_computed_at;
