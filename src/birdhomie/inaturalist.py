"""iNaturalist API client for fetching species information."""

import logging
import time
import requests
from pathlib import Path
from typing import Optional, Dict
from . import database as db
from .constants import SPECIES_IMAGES_DIR
from .utils import retry_on_failure

logger = logging.getLogger(__name__)

INATURALIST_API_BASE = "https://api.inaturalist.org/v1"
REQUEST_TIMEOUT = 10
RATE_LIMIT_DELAY = 0.5


def normalize_species_name(name: str) -> str:
    """Normalize species name from classifier output to search format.

    Converts 'PARUS MAJOR' or 'PARUS_MAJOR' to 'Parus major'.
    """
    return name.replace("_", " ").title()


def parse_inaturalist_url(url: str) -> Optional[int]:
    """Extract taxon_id from iNaturalist URL.

    Example: https://www.inaturalist.org/taxa/13094 -> 13094
    """
    import re

    match = re.search(r"/taxa/(\d+)", url)
    if match:
        return int(match.group(1))
    return None


@retry_on_failure(max_attempts=3, delay=1.0)
def fetch_species_by_taxon_id(taxon_id: int) -> Optional[Dict]:
    """Fetch species information by taxon_id from iNaturalist API.

    Returns dict with taxon_id, scientific_name, common_name_en, common_name_de, wikipedia_url, image data
    """
    logger.info("fetching_inaturalist_taxon", extra={"taxon_id": taxon_id})

    try:
        response = requests.get(
            f"{INATURALIST_API_BASE}/taxa/{taxon_id}", timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("results"):
            logger.warning("taxon_not_found", extra={"taxon_id": taxon_id})
            return None

        taxon = data["results"][0]

        result = {
            "taxon_id": taxon.get("id"),
            "scientific_name": taxon.get("name"),
            "common_name_en": None,
            "common_name_de": None,
            "wikipedia_url": taxon.get("wikipedia_url"),
            "image_url": None,
            "image_attribution": None,
        }

        # Get English common name
        if taxon.get("preferred_common_name"):
            result["common_name_en"] = taxon.get("preferred_common_name")

        # Get image
        if taxon.get("default_photo"):
            photo = taxon["default_photo"]
            result["image_url"] = photo.get("medium_url")
            result["image_attribution"] = photo.get("attribution")

        # Fetch German common name separately
        time.sleep(RATE_LIMIT_DELAY)
        de_response = requests.get(
            f"{INATURALIST_API_BASE}/taxa/{taxon_id}",
            params={"locale": "de"},
            timeout=REQUEST_TIMEOUT,
        )
        if de_response.ok:
            de_data = de_response.json()
            if de_data.get("results"):
                de_taxon = de_data["results"][0]
                result["common_name_de"] = de_taxon.get("preferred_common_name")

        return result

    except requests.RequestException as e:
        logger.error(
            "inaturalist_api_error", extra={"taxon_id": taxon_id, "error": str(e)}
        )
        raise


@retry_on_failure(max_attempts=3, delay=1.0)
def fetch_species_from_api(scientific_name: str) -> Optional[Dict]:
    """Fetch species information from iNaturalist API.

    Returns dict with taxon_id, common_name_en, common_name_de, wikipedia_url, image data
    """
    normalized = normalize_species_name(scientific_name)

    logger.info("fetching_inaturalist_data", extra={"species": normalized})

    try:
        response = requests.get(
            f"{INATURALIST_API_BASE}/taxa",
            params={"q": normalized, "rank": "species", "per_page": 1},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("results"):
            logger.warning("species_not_found", extra={"species": normalized})
            return None

        taxon = data["results"][0]

        result = {
            "taxon_id": taxon.get("id"),
            "scientific_name": taxon.get("name", normalized),
            "common_name_en": None,
            "common_name_de": None,
            "wikipedia_url": taxon.get("wikipedia_url"),
            "image_url": None,
            "image_attribution": None,
        }

        # Get English common name
        if taxon.get("preferred_common_name"):
            result["common_name_en"] = taxon.get("preferred_common_name")

        # Get image
        if taxon.get("default_photo"):
            photo = taxon["default_photo"]
            result["image_url"] = photo.get("medium_url")
            result["image_attribution"] = photo.get("attribution")

        # Fetch German common name separately
        time.sleep(RATE_LIMIT_DELAY)
        de_response = requests.get(
            f"{INATURALIST_API_BASE}/taxa",
            params={"q": normalized, "rank": "species", "per_page": 1, "locale": "de"},
            timeout=REQUEST_TIMEOUT,
        )
        if de_response.ok:
            de_data = de_response.json()
            if de_data.get("results"):
                de_taxon = de_data["results"][0]
                result["common_name_de"] = de_taxon.get("preferred_common_name")

        return result

    except requests.RequestException as e:
        logger.error(
            "inaturalist_api_error", extra={"species": normalized, "error": str(e)}
        )
        raise


def download_species_image(image_url: str, taxon_id: int) -> Optional[Path]:
    """Download species image to local storage.

    Args:
        image_url: URL of the image to download
        taxon_id: iNaturalist taxon ID

    Returns:
        Path to downloaded image or None on failure
    """
    if not image_url:
        return None

    SPECIES_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Use taxon_id_1.jpg as filename (allows for multiple images per species)
    local_path = SPECIES_IMAGES_DIR / f"{taxon_id}_1.jpg"

    if local_path.exists():
        logger.debug("species_image_exists", extra={"path": str(local_path)})
        return local_path

    try:
        logger.info(
            "downloading_species_image", extra={"taxon_id": taxon_id, "url": image_url}
        )

        response = requests.get(image_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        local_path.write_bytes(response.content)

        logger.info(
            "species_image_downloaded",
            extra={"taxon_id": taxon_id, "path": str(local_path)},
        )

        return local_path

    except requests.RequestException as e:
        logger.error(
            "image_download_failed",
            extra={"taxon_id": taxon_id, "url": image_url, "error": str(e)},
        )
        return None


def get_or_create_taxon(scientific_name: str) -> Optional[int]:
    """Get or create iNaturalist taxon record.

    Args:
        scientific_name: Scientific name of the species

    Returns:
        taxon_id or None on failure
    """
    normalized = normalize_species_name(scientific_name)

    # Check if already in database
    with db.get_connection() as conn:
        existing = conn.execute(
            """
            SELECT taxon_id FROM inaturalist_taxa
            WHERE scientific_name = ?
        """,
            (normalized,),
        ).fetchone()

        if existing:
            return existing["taxon_id"]

    # Fetch from API
    time.sleep(RATE_LIMIT_DELAY)

    try:
        api_data = fetch_species_from_api(scientific_name)

        if not api_data:
            return None

        taxon_id = api_data["taxon_id"]

        # Insert into database
        with db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO inaturalist_taxa
                (taxon_id, scientific_name, common_name_en, common_name_de,
                 wikipedia_url, fetched_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(taxon_id) DO UPDATE SET
                    common_name_en = excluded.common_name_en,
                    common_name_de = excluded.common_name_de,
                    wikipedia_url = excluded.wikipedia_url,
                    fetched_at = CURRENT_TIMESTAMP
            """,
                (
                    taxon_id,
                    api_data["scientific_name"],
                    api_data["common_name_en"],
                    api_data["common_name_de"],
                    api_data["wikipedia_url"],
                ),
            )

        # Download image if available
        if api_data["image_url"]:
            local_path = download_species_image(api_data["image_url"], taxon_id)

            if local_path:
                with db.get_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO species_images
                        (taxon_id, original_url, local_path, attribution,
                         is_default, fetched_at)
                        VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                        ON CONFLICT DO NOTHING
                    """,
                        (
                            taxon_id,
                            api_data["image_url"],
                            str(local_path),
                            api_data["image_attribution"],
                        ),
                    )

        logger.info(
            "taxon_created",
            extra={
                "taxon_id": taxon_id,
                "scientific_name": api_data["scientific_name"],
            },
        )

        return taxon_id

    except Exception as e:
        logger.error(
            "taxon_creation_failed",
            extra={"scientific_name": scientific_name, "error": str(e)},
        )
        return None


def get_or_create_taxon_by_id(taxon_id: int) -> Optional[int]:
    """Get or create iNaturalist taxon record by taxon_id.

    Args:
        taxon_id: iNaturalist taxon ID

    Returns:
        taxon_id or None on failure
    """
    # Check if already in database
    with db.get_connection() as conn:
        existing = conn.execute(
            """
            SELECT taxon_id FROM inaturalist_taxa
            WHERE taxon_id = ?
        """,
            (taxon_id,),
        ).fetchone()

        if existing:
            return existing["taxon_id"]

    # Fetch from API
    time.sleep(RATE_LIMIT_DELAY)

    try:
        api_data = fetch_species_by_taxon_id(taxon_id)

        if not api_data:
            return None

        # Insert into database
        with db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO inaturalist_taxa
                (taxon_id, scientific_name, common_name_en, common_name_de,
                 wikipedia_url, fetched_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(taxon_id) DO UPDATE SET
                    scientific_name = excluded.scientific_name,
                    common_name_en = excluded.common_name_en,
                    common_name_de = excluded.common_name_de,
                    wikipedia_url = excluded.wikipedia_url,
                    fetched_at = CURRENT_TIMESTAMP
            """,
                (
                    taxon_id,
                    api_data["scientific_name"],
                    api_data["common_name_en"],
                    api_data["common_name_de"],
                    api_data["wikipedia_url"],
                ),
            )

        # Download image if available
        if api_data["image_url"]:
            local_path = download_species_image(api_data["image_url"], taxon_id)

            if local_path:
                with db.get_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO species_images
                        (taxon_id, original_url, local_path, attribution,
                         is_default, fetched_at)
                        VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                        ON CONFLICT DO NOTHING
                    """,
                        (
                            taxon_id,
                            api_data["image_url"],
                            str(local_path),
                            api_data["image_attribution"],
                        ),
                    )

        logger.info(
            "taxon_created_by_id",
            extra={
                "taxon_id": taxon_id,
                "scientific_name": api_data["scientific_name"],
            },
        )

        return taxon_id

    except Exception as e:
        logger.error(
            "taxon_creation_by_id_failed", extra={"taxon_id": taxon_id, "error": str(e)}
        )
        return None
