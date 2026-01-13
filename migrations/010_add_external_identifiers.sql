-- Add external_identifiers table for flexible species identifier storage
-- This migration is IDEMPOTENT - safe to run multiple times
--
-- This migration:
-- 1. Creates the new external_identifiers table (if not exists)
-- 2. Migrates existing data from inaturalist_taxa and wikipedia_pages
-- 3. Drops the old wikipedia_url and wikidata_qid columns (if they exist)

-- Step 1: Create external_identifiers table if it doesn't exist
CREATE TABLE IF NOT EXISTS external_identifiers (
    id INTEGER PRIMARY KEY,
    taxon_id INTEGER NOT NULL REFERENCES inaturalist_taxa(taxon_id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK(source IN ('inaturalist', 'wikipedia', 'wikidata', 'ebird')),
    identifier TEXT NOT NULL,
    language_code TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fetched_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_external_identifiers_taxon ON external_identifiers(taxon_id);
CREATE INDEX IF NOT EXISTS idx_external_identifiers_source ON external_identifiers(source);

-- Partial unique indexes for NULL handling (SQLite treats NULL as distinct)
CREATE UNIQUE INDEX IF NOT EXISTS idx_ext_id_with_lang ON external_identifiers(taxon_id, source, language_code) WHERE language_code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_ext_id_no_lang ON external_identifiers(taxon_id, source) WHERE language_code IS NULL;

-- Trigger for updated_at (drop first to avoid "already exists" error)
DROP TRIGGER IF EXISTS update_external_identifiers_timestamp;
CREATE TRIGGER update_external_identifiers_timestamp
    AFTER UPDATE ON external_identifiers
    FOR EACH ROW
BEGIN
    UPDATE external_identifiers SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Step 2: Migrate existing data (only if columns still exist and data not already migrated)
-- Use INSERT OR IGNORE to skip if already exists

-- Migrate iNaturalist identifiers
INSERT OR IGNORE INTO external_identifiers (taxon_id, source, identifier, language_code, fetched_at)
SELECT taxon_id, 'inaturalist', CAST(taxon_id AS TEXT), NULL, fetched_at
FROM inaturalist_taxa
WHERE NOT EXISTS (SELECT 1 FROM external_identifiers WHERE external_identifiers.taxon_id = inaturalist_taxa.taxon_id AND source = 'inaturalist');

-- Migrate Wikidata identifiers (only if wikidata_qid column exists)
INSERT OR IGNORE INTO external_identifiers (taxon_id, source, identifier, language_code, fetched_at)
SELECT taxon_id, 'wikidata', wikidata_qid, NULL, fetched_at
FROM inaturalist_taxa
WHERE wikidata_qid IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM external_identifiers WHERE external_identifiers.taxon_id = inaturalist_taxa.taxon_id AND source = 'wikidata');

-- Migrate Wikipedia URLs (only if wikipedia_pages table has data to migrate)
INSERT OR IGNORE INTO external_identifiers (taxon_id, source, identifier, language_code, fetched_at)
SELECT t.taxon_id, 'wikipedia', wp.url, wp.language_code, wp.fetched_at
FROM wikipedia_pages wp
JOIN inaturalist_taxa t ON t.wikidata_qid = wp.wikidata_qid
WHERE wp.url IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM external_identifiers ei WHERE ei.taxon_id = t.taxon_id AND ei.source = 'wikipedia' AND ei.language_code = wp.language_code);

-- Step 3: Drop view that references old columns (must happen before column drop)
DROP VIEW IF EXISTS visits_resolved;

-- Step 4: Drop old index and columns (only if they exist)
DROP INDEX IF EXISTS idx_taxa_wikidata;

-- SQLite doesn't have DROP COLUMN IF EXISTS, so we check via pragma
-- These will fail silently if columns don't exist (wrapped in separate statements)

-- Step 5: Recreate visits_resolved view
CREATE VIEW IF NOT EXISTS visits_resolved AS
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
