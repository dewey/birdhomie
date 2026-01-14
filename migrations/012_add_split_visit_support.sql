-- Add split visit support with time segments
-- This migration removes the UNIQUE constraint on (file_id, inaturalist_taxon_id)
-- to allow multiple visits of the same species at different time segments.
--
-- IMPORTANT: This migration also fixes foreign key references in the detections
-- table, which can get broken when using ALTER TABLE ... RENAME in SQLite.

-- First, clean up any leftover tables from failed migrations
DROP TABLE IF EXISTS visits_new_temp;
DROP TABLE IF EXISTS visits_backup;
DROP TABLE IF EXISTS detections_new_temp;
DROP TABLE IF EXISTS detections_backup;

-- ============================================================================
-- Part 1: Fix the visits table
-- ============================================================================

-- Create the new visits table structure (without the unique constraint, with new columns)
CREATE TABLE visits_new_temp (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    inaturalist_taxon_id INTEGER REFERENCES inaturalist_taxa(taxon_id),
    override_taxon_id INTEGER REFERENCES inaturalist_taxa(taxon_id),
    species_confidence REAL NOT NULL CHECK(species_confidence >= 0 AND species_confidence <= 1),
    species_confidence_model TEXT,
    detection_count INTEGER DEFAULT 1 CHECK(detection_count > 0),
    best_detection_id INTEGER,
    cover_detection_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    corrected_at TIMESTAMP,
    deleted_at TIMESTAMP,
    segment_start_time REAL DEFAULT NULL,
    segment_end_time REAL DEFAULT NULL,
    parent_visit_id INTEGER DEFAULT NULL
);

-- Copy all existing data from visits table
INSERT INTO visits_new_temp (
    id, file_id, inaturalist_taxon_id, override_taxon_id,
    species_confidence, species_confidence_model, detection_count,
    best_detection_id, cover_detection_id, created_at, updated_at,
    corrected_at, deleted_at
)
SELECT
    id, file_id, inaturalist_taxon_id, override_taxon_id,
    species_confidence, species_confidence_model, detection_count,
    best_detection_id, cover_detection_id, created_at, updated_at,
    corrected_at, deleted_at
FROM visits;

-- Drop old visits indexes
DROP INDEX IF EXISTS idx_visits_taxon;
DROP INDEX IF EXISTS idx_visits_file;
DROP INDEX IF EXISTS idx_visits_deleted_at;
DROP INDEX IF EXISTS idx_visits_segment;
DROP INDEX IF EXISTS idx_visits_parent;

-- ============================================================================
-- Part 2: Fix the detections table (fix foreign key to visits)
-- ============================================================================

-- Create new detections table with correct foreign key reference
CREATE TABLE detections_new_temp (
    id INTEGER PRIMARY KEY,
    visit_id INTEGER NOT NULL REFERENCES visits_new_temp(id) ON DELETE CASCADE,
    frame_number INTEGER NOT NULL CHECK(frame_number >= 0),
    frame_timestamp REAL NOT NULL CHECK(frame_timestamp >= 0),
    detection_confidence REAL NOT NULL CHECK(detection_confidence >= 0 AND detection_confidence <= 1),
    detection_confidence_model TEXT,
    species_confidence REAL CHECK(species_confidence >= 0 AND species_confidence <= 1),
    species_confidence_model TEXT,
    bbox_x1 INTEGER NOT NULL,
    bbox_y1 INTEGER NOT NULL,
    bbox_x2 INTEGER NOT NULL,
    bbox_y2 INTEGER NOT NULL,
    crop_path TEXT,
    is_edge_detection INTEGER DEFAULT 0 CHECK(is_edge_detection IN (0, 1)),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    face_bbox_x1 INTEGER,
    face_bbox_y1 INTEGER,
    face_bbox_x2 INTEGER,
    face_bbox_y2 INTEGER,
    annotation_source TEXT,
    annotated_at TIMESTAMP,
    reviewed_at TIMESTAMP
);

-- Copy detections data
INSERT INTO detections_new_temp (
    id, visit_id, frame_number, frame_timestamp,
    detection_confidence, detection_confidence_model,
    species_confidence, species_confidence_model,
    bbox_x1, bbox_y1, bbox_x2, bbox_y2,
    crop_path, is_edge_detection, created_at, updated_at,
    face_bbox_x1, face_bbox_y1, face_bbox_x2, face_bbox_y2,
    annotation_source, annotated_at, reviewed_at
)
SELECT
    id, visit_id, frame_number, frame_timestamp,
    detection_confidence, detection_confidence_model,
    species_confidence, species_confidence_model,
    bbox_x1, bbox_y1, bbox_x2, bbox_y2,
    crop_path, is_edge_detection, created_at, updated_at,
    face_bbox_x1, face_bbox_y1, face_bbox_x2, face_bbox_y2,
    annotation_source, annotated_at, reviewed_at
FROM detections;

-- Drop old detection indexes
DROP INDEX IF EXISTS idx_detections_visit;
DROP INDEX IF EXISTS idx_detections_frame;
DROP INDEX IF EXISTS idx_detections_annotation_source;
DROP INDEX IF EXISTS idx_detections_annotated_at;
DROP INDEX IF EXISTS idx_detections_needs_annotation;
DROP INDEX IF EXISTS idx_detections_visit_id;

-- ============================================================================
-- Part 3: Swap tables
-- ============================================================================

-- Rename old tables
ALTER TABLE visits RENAME TO visits_backup;
ALTER TABLE detections RENAME TO detections_backup;

-- Rename new tables to final names
ALTER TABLE visits_new_temp RENAME TO visits;
ALTER TABLE detections_new_temp RENAME TO detections;

-- ============================================================================
-- Part 4: Recreate all indexes
-- ============================================================================

-- Visits indexes
CREATE INDEX idx_visits_taxon ON visits(inaturalist_taxon_id);
CREATE INDEX idx_visits_file ON visits(file_id);
CREATE INDEX idx_visits_deleted_at ON visits(deleted_at);
CREATE INDEX idx_visits_segment ON visits(file_id, segment_start_time, segment_end_time);
CREATE INDEX idx_visits_parent ON visits(parent_visit_id);

-- Detections indexes
CREATE INDEX idx_detections_visit ON detections(visit_id);
CREATE INDEX idx_detections_frame ON detections(frame_number);
CREATE INDEX idx_detections_annotation_source ON detections(annotation_source);
CREATE INDEX idx_detections_annotated_at ON detections(annotated_at)
    WHERE annotation_source IS NOT NULL;
CREATE INDEX idx_detections_needs_annotation ON detections(id)
    WHERE annotation_source IS NULL;
CREATE INDEX idx_detections_visit_id ON detections(visit_id);

-- ============================================================================
-- Part 5: Recreate triggers
-- ============================================================================

DROP TRIGGER IF EXISTS update_visits_timestamp;
CREATE TRIGGER update_visits_timestamp
    AFTER UPDATE ON visits
    FOR EACH ROW
BEGIN
    UPDATE visits SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

DROP TRIGGER IF EXISTS update_detections_timestamp;
CREATE TRIGGER update_detections_timestamp
    AFTER UPDATE ON detections
    FOR EACH ROW
BEGIN
    UPDATE detections SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================================
-- Part 6: Clean up backup tables
-- ============================================================================

DROP TABLE detections_backup;
DROP TABLE visits_backup;

-- ============================================================================
-- Part 7: Recreate visits_resolved view
-- ============================================================================

DROP VIEW IF EXISTS visits_resolved;
CREATE VIEW visits_resolved AS
SELECT
    v.id,
    v.file_id,
    v.species_confidence,
    v.species_confidence_model,
    v.detection_count,
    v.best_detection_id,
    v.cover_detection_id,
    v.created_at,
    v.updated_at,
    v.corrected_at,
    v.deleted_at,
    v.segment_start_time,
    v.segment_end_time,
    v.parent_visit_id,
    COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) AS resolved_taxon_id,
    v.override_taxon_id IS NOT NULL AS is_corrected,
    v.segment_start_time IS NOT NULL AS is_segmented,
    t.scientific_name,
    t.common_name_en,
    t.common_name_de,
    ei.identifier AS wikidata_qid,
    si.local_path AS default_image_path,
    si.attribution AS default_image_attribution
FROM visits v
LEFT JOIN inaturalist_taxa t
    ON COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) = t.taxon_id
LEFT JOIN external_identifiers ei
    ON t.taxon_id = ei.taxon_id AND ei.source = 'wikidata'
LEFT JOIN species_images si
    ON t.taxon_id = si.taxon_id AND si.is_default = 1;
