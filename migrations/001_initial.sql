-- Initial schema for birdhomie database

-- Files downloaded from UniFi Protect
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT NOT NULL,
    source_event_id TEXT,
    event_start TIMESTAMP NOT NULL,
    event_end TIMESTAMP,
    duration_seconds REAL,
    output_dir TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'success', 'failed')),
    error_message TEXT
);

-- One visit = one species observed in one file
CREATE TABLE visits (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    inaturalist_taxon_id INTEGER REFERENCES inaturalist_taxa(taxon_id),
    override_taxon_id INTEGER REFERENCES inaturalist_taxa(taxon_id),
    species_confidence REAL NOT NULL CHECK(species_confidence >= 0 AND species_confidence <= 1),
    species_confidence_model TEXT,
    detection_count INTEGER DEFAULT 1 CHECK(detection_count > 0),
    best_detection_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    corrected_at TIMESTAMP,
    UNIQUE(file_id, inaturalist_taxon_id)
);

-- Individual detections for debugging and analysis
CREATE TABLE detections (
    id INTEGER PRIMARY KEY,
    visit_id INTEGER NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- iNaturalist taxa (canonical species source)
CREATE TABLE inaturalist_taxa (
    taxon_id INTEGER PRIMARY KEY,
    scientific_name TEXT NOT NULL UNIQUE,
    common_name_en TEXT,
    common_name_de TEXT,
    wikipedia_url TEXT,
    wikidata_qid TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fetched_at TIMESTAMP
);

-- Species images (multiple per taxon, stored locally)
CREATE TABLE species_images (
    id INTEGER PRIMARY KEY,
    taxon_id INTEGER NOT NULL REFERENCES inaturalist_taxa(taxon_id) ON DELETE CASCADE,
    original_url TEXT NOT NULL,
    local_path TEXT,
    attribution TEXT,
    is_default INTEGER DEFAULT 0 CHECK(is_default IN (0, 1)),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fetched_at TIMESTAMP
);

-- Wikipedia pages (multi-language, linked via Wikidata QID)
CREATE TABLE wikipedia_pages (
    wikidata_qid TEXT NOT NULL,
    language_code TEXT NOT NULL,
    page_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    extract TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fetched_at TIMESTAMP,
    PRIMARY KEY (wikidata_qid, language_code)
);

-- Background task tracking
CREATE TABLE task_runs (
    id INTEGER PRIMARY KEY,
    task_type TEXT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT DEFAULT 'running' CHECK(status IN ('running', 'success', 'failed')),
    items_processed INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0,
    error_message TEXT,
    duration_seconds REAL,
    hostname TEXT,
    pid INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indices
CREATE INDEX idx_files_status ON files(status);
CREATE INDEX idx_files_event_start ON files(event_start);
CREATE INDEX idx_files_hash ON files(file_hash);
CREATE INDEX idx_visits_taxon ON visits(inaturalist_taxon_id);
CREATE INDEX idx_visits_file ON visits(file_id);
CREATE INDEX idx_detections_visit ON detections(visit_id);
CREATE INDEX idx_detections_frame ON detections(frame_number);
CREATE INDEX idx_taxa_scientific_name ON inaturalist_taxa(scientific_name);
CREATE INDEX idx_taxa_wikidata ON inaturalist_taxa(wikidata_qid);
CREATE INDEX idx_species_images_taxon ON species_images(taxon_id);
CREATE INDEX idx_wikipedia_qid ON wikipedia_pages(wikidata_qid);

-- Triggers to automatically update updated_at timestamp
CREATE TRIGGER update_files_timestamp
    AFTER UPDATE ON files
    FOR EACH ROW
BEGIN
    UPDATE files SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER update_visits_timestamp
    AFTER UPDATE ON visits
    FOR EACH ROW
BEGIN
    UPDATE visits SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER update_detections_timestamp
    AFTER UPDATE ON detections
    FOR EACH ROW
BEGIN
    UPDATE detections SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER update_inaturalist_taxa_timestamp
    AFTER UPDATE ON inaturalist_taxa
    FOR EACH ROW
BEGIN
    UPDATE inaturalist_taxa SET updated_at = CURRENT_TIMESTAMP WHERE taxon_id = NEW.taxon_id;
END;

CREATE TRIGGER update_species_images_timestamp
    AFTER UPDATE ON species_images
    FOR EACH ROW
BEGIN
    UPDATE species_images SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER update_wikipedia_pages_timestamp
    AFTER UPDATE ON wikipedia_pages
    FOR EACH ROW
BEGIN
    UPDATE wikipedia_pages SET updated_at = CURRENT_TIMESTAMP WHERE wikidata_qid = NEW.wikidata_qid AND language_code = NEW.language_code;
END;

CREATE TRIGGER update_task_runs_timestamp
    AFTER UPDATE ON task_runs
    FOR EACH ROW
BEGIN
    UPDATE task_runs SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Helper view for resolved species with full metadata
CREATE VIEW visits_resolved AS
SELECT
    v.id,
    v.file_id,
    v.species_confidence,
    v.species_confidence_model,
    v.detection_count,
    v.best_detection_id,
    v.created_at,
    v.updated_at,
    v.corrected_at,
    COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) AS resolved_taxon_id,
    v.override_taxon_id IS NOT NULL AS is_corrected,
    t.scientific_name,
    t.common_name_en,
    t.common_name_de,
    t.wikidata_qid,
    si.local_path AS default_image_path,
    si.attribution AS default_image_attribution
FROM visits v
LEFT JOIN inaturalist_taxa t
    ON COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) = t.taxon_id
LEFT JOIN species_images si
    ON t.taxon_id = si.taxon_id AND si.is_default = 1;
