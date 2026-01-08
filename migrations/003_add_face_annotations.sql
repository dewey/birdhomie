-- Add face bbox annotation fields to detections table
ALTER TABLE detections ADD COLUMN face_bbox_x1 INTEGER;
ALTER TABLE detections ADD COLUMN face_bbox_y1 INTEGER;
ALTER TABLE detections ADD COLUMN face_bbox_x2 INTEGER;
ALTER TABLE detections ADD COLUMN face_bbox_y2 INTEGER;

-- Track annotation source and timing
-- Values: 'machine', 'human_confirmed', 'human_corrected', 'no_face', NULL (not annotated)
ALTER TABLE detections ADD COLUMN annotation_source TEXT;
ALTER TABLE detections ADD COLUMN annotated_at TIMESTAMP;
ALTER TABLE detections ADD COLUMN reviewed_at TIMESTAMP;

-- Index for efficient queries
CREATE INDEX idx_detections_annotation_source ON detections(annotation_source);
CREATE INDEX idx_detections_annotated_at ON detections(annotated_at)
  WHERE annotation_source IS NOT NULL;

-- Index for finding unannotated crops
CREATE INDEX idx_detections_needs_annotation ON detections(id)
  WHERE annotation_source IS NULL;
