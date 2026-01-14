-- Performance indexes for frequently queried columns

-- Visits table indexes
CREATE INDEX IF NOT EXISTS idx_visits_taxon_id ON visits(inaturalist_taxon_id);
CREATE INDEX IF NOT EXISTS idx_visits_override_taxon_id ON visits(override_taxon_id) WHERE override_taxon_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_visits_file_id ON visits(file_id);
CREATE INDEX IF NOT EXISTS idx_visits_deleted_at ON visits(deleted_at) WHERE deleted_at IS NULL;

-- Detections table indexes
CREATE INDEX IF NOT EXISTS idx_detections_visit_id ON detections(visit_id);
CREATE INDEX IF NOT EXISTS idx_detections_annotation_source ON detections(annotation_source) WHERE annotation_source IS NOT NULL;

-- Files table indexes
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_event_start ON files(event_start);

-- External identifiers for species lookups
CREATE INDEX IF NOT EXISTS idx_external_identifiers_taxon_source ON external_identifiers(taxon_id, source);
