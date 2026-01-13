"""Wikipedia and Wikidata API client for fetching species descriptions."""

import logging
import time
import re
import requests
from urllib.parse import unquote
from typing import Optional, Dict
from . import database as db
from .utils import retry_on_failure

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10
RATE_LIMIT_DELAY = 0.5


def extract_title_from_url(wikipedia_url: str) -> Optional[str]:
    """Extract the article title from a Wikipedia URL.

    Example: https://en.wikipedia.org/wiki/Great_tit -> Great_tit
    """
    if not wikipedia_url:
        return None

    match = re.search(r"wikipedia\.org/wiki/(.+)$", wikipedia_url)
    if match:
        return unquote(match.group(1))
    return None


def get_wikipedia_language(wikipedia_url: str) -> str:
    """Extract language code from Wikipedia URL.

    Example: https://en.wikipedia.org/wiki/Great_tit -> en
    """
    match = re.search(r"https?://([a-z]{2})\.wikipedia\.org", wikipedia_url)
    if match:
        return match.group(1)
    return "en"


@retry_on_failure(max_attempts=3, delay=1.0)
def fetch_wikidata_qid(wikipedia_url: str) -> Optional[str]:
    """Fetch Wikidata QID from Wikipedia article URL.

    Args:
        wikipedia_url: Wikipedia article URL

    Returns:
        Wikidata QID (e.g., 'Q25394') or None
    """
    title = extract_title_from_url(wikipedia_url)
    lang = get_wikipedia_language(wikipedia_url)

    if not title:
        return None

    try:
        url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "titles": title,
            "prop": "pageprops",
            "format": "json",
        }

        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": "BirdHomie/1.0"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            pageprops = page.get("pageprops", {})
            qid = pageprops.get("wikibase_item")
            if qid:
                return qid

        return None

    except requests.RequestException as e:
        logger.error(
            "wikidata_qid_fetch_failed", extra={"url": wikipedia_url, "error": str(e)}
        )
        raise


@retry_on_failure(max_attempts=3, delay=1.0)
def fetch_wikipedia_page_by_qid(wikidata_qid: str, language: str) -> Optional[Dict]:
    """Fetch Wikipedia page information by Wikidata QID and language.

    Args:
        wikidata_qid: Wikidata QID (e.g., 'Q25394')
        language: Language code (e.g., 'en', 'de')

    Returns:
        Dict with page_id, title, url, extract
    """
    try:
        # First, get the page title for this language
        url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities",
            "ids": wikidata_qid,
            "props": "sitelinks",
            "format": "json",
        }

        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": "BirdHomie/1.0"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        entities = data.get("entities", {})
        if wikidata_qid not in entities:
            return None

        sitelinks = entities[wikidata_qid].get("sitelinks", {})
        site_key = f"{language}wiki"

        if site_key not in sitelinks:
            logger.debug(
                "wikipedia_page_not_found",
                extra={"qid": wikidata_qid, "language": language},
            )
            return None

        title = sitelinks[site_key]["title"]

        # Now fetch the page summary
        time.sleep(RATE_LIMIT_DELAY)

        summary_url = (
            f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{title}"
        )
        summary_response = requests.get(
            summary_url,
            headers={"User-Agent": "BirdHomie/1.0"},
            timeout=REQUEST_TIMEOUT,
        )

        if summary_response.status_code == 404:
            return None

        summary_response.raise_for_status()
        summary_data = summary_response.json()

        return {
            "page_id": summary_data.get("pageid"),
            "title": summary_data.get("title"),
            "url": summary_data.get("content_urls", {}).get("desktop", {}).get("page"),
            "extract": summary_data.get("extract"),
        }

    except requests.RequestException as e:
        logger.error(
            "wikipedia_page_fetch_failed",
            extra={"qid": wikidata_qid, "language": language, "error": str(e)},
        )
        raise


def fetch_and_store_wikipedia_pages(taxon_id: int):
    """Fetch Wikipedia pages for all supported languages and store in database.

    Args:
        taxon_id: iNaturalist taxon ID
    """
    # Get the taxon's wikidata_qid from external_identifiers
    with db.get_connection() as conn:
        taxon = conn.execute(
            """
            SELECT taxon_id FROM inaturalist_taxa WHERE taxon_id = ?
        """,
            (taxon_id,),
        ).fetchone()

        if not taxon:
            return

        # Get wikidata_qid from external_identifiers
        wikidata_row = conn.execute(
            """
            SELECT identifier FROM external_identifiers
            WHERE taxon_id = ? AND source = 'wikidata'
        """,
            (taxon_id,),
        ).fetchone()

        wikidata_qid = wikidata_row["identifier"] if wikidata_row else None

    if not wikidata_qid:
        return

    # Fetch Wikipedia pages for each language
    for language in ["en", "de"]:
        # Check if already cached
        with db.get_connection() as conn:
            existing = conn.execute(
                """
                SELECT page_id FROM wikipedia_pages
                WHERE wikidata_qid = ? AND language_code = ?
            """,
                (wikidata_qid, language),
            ).fetchone()

            if existing:
                continue

        time.sleep(RATE_LIMIT_DELAY)

        try:
            page_data = fetch_wikipedia_page_by_qid(wikidata_qid, language)

            if page_data:
                with db.get_connection() as conn:
                    # Store in wikipedia_pages table (for extracts)
                    conn.execute(
                        """
                        INSERT INTO wikipedia_pages
                        (wikidata_qid, language_code, page_id, title, url, extract, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(wikidata_qid, language_code) DO UPDATE SET
                            page_id = excluded.page_id,
                            title = excluded.title,
                            url = excluded.url,
                            extract = excluded.extract,
                            fetched_at = CURRENT_TIMESTAMP
                    """,
                        (
                            wikidata_qid,
                            language,
                            page_data["page_id"],
                            page_data["title"],
                            page_data["url"],
                            page_data["extract"],
                        ),
                    )

                    # Also store Wikipedia URL in external_identifiers
                    if page_data["url"]:
                        conn.execute(
                            """
                            INSERT INTO external_identifiers (taxon_id, source, identifier, language_code, fetched_at)
                            VALUES (?, 'wikipedia', ?, ?, CURRENT_TIMESTAMP)
                            ON CONFLICT(taxon_id, source, COALESCE(language_code, '')) DO UPDATE SET
                                identifier = excluded.identifier,
                                fetched_at = CURRENT_TIMESTAMP
                        """,
                            (taxon_id, page_data["url"], language),
                        )

                logger.info(
                    "wikipedia_page_stored",
                    extra={
                        "taxon_id": taxon_id,
                        "language": language,
                        "title": page_data["title"],
                    },
                )

        except Exception as e:
            logger.error(
                "wikipedia_page_fetch_error",
                extra={"taxon_id": taxon_id, "language": language, "error": str(e)},
            )
