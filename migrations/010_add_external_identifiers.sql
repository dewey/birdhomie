-- Add external_identifiers table for flexible species identifier storage
-- This migration:
-- 1. Creates the new external_identifiers table
-- 2. Migrates existing data from inaturalist_taxa and wikipedia_pages
-- 3. Drops the old wikipedia_url and wikidata_qid columns
--
-- This is a ONE-WAY migration - ensure you have a database backup before applying!

-- Step 1: Create external_identifiers table
CREATE TABLE external_identifiers (
    id INTEGER PRIMARY KEY,
    taxon_id INTEGER NOT NULL REFERENCES inaturalist_taxa(taxon_id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK(source IN ('inaturalist', 'wikipedia', 'wikidata', 'ebird')),
    identifier TEXT NOT NULL,
    language_code TEXT DEFAULT NULL,  -- NULL for language-agnostic resources, language code for Wikipedia
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fetched_at TIMESTAMP,
    UNIQUE(taxon_id, source, COALESCE(language_code, ''))  -- Use COALESCE to treat NULL as '' for uniqueness
);

CREATE INDEX idx_external_identifiers_taxon ON external_identifiers(taxon_id);
CREATE INDEX idx_external_identifiers_source ON external_identifiers(source);

CREATE TRIGGER update_external_identifiers_timestamp
    AFTER UPDATE ON external_identifiers
    FOR EACH ROW
BEGIN
    UPDATE external_identifiers SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Step 2: Migrate existing data

-- Migrate iNaturalist identifiers (one per taxon)
INSERT INTO external_identifiers (taxon_id, source, identifier, language_code, fetched_at)
SELECT taxon_id, 'inaturalist', CAST(taxon_id AS TEXT), NULL, fetched_at
FROM inaturalist_taxa;

-- Migrate Wikidata identifiers (where available)
INSERT INTO external_identifiers (taxon_id, source, identifier, language_code, fetched_at)
SELECT taxon_id, 'wikidata', wikidata_qid, NULL, fetched_at
FROM inaturalist_taxa
WHERE wikidata_qid IS NOT NULL;

-- Migrate Wikipedia URLs from wikipedia_pages table (one per language per taxon)
INSERT INTO external_identifiers (taxon_id, source, identifier, language_code, fetched_at)
SELECT t.taxon_id, 'wikipedia', wp.url, wp.language_code, wp.fetched_at
FROM wikipedia_pages wp
JOIN inaturalist_taxa t ON t.wikidata_qid = wp.wikidata_qid
WHERE wp.url IS NOT NULL;

-- Step 3: Drop the index on wikidata_qid BEFORE dropping the column
DROP INDEX IF EXISTS idx_taxa_wikidata;

-- Step 4: Drop deprecated columns from inaturalist_taxa
-- These are now stored in external_identifiers
ALTER TABLE inaturalist_taxa DROP COLUMN wikipedia_url;
ALTER TABLE inaturalist_taxa DROP COLUMN wikidata_qid;

-- Step 5: Update visits_resolved view to get wikidata_qid from external_identifiers
DROP VIEW IF EXISTS visits_resolved;
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
