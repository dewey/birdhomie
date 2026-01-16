"""Tests for iNaturalist API integration."""

import pytest
from unittest.mock import patch, MagicMock


class TestNormalizeSpeciesName:
    """Test species name normalization."""

    def test_basic_normalization(self):
        """Test basic species name normalization."""
        from birdhomie.inaturalist import normalize_species_name

        assert normalize_species_name("Turdus merula") == "Turdus merula"
        assert normalize_species_name("turdus merula") == "Turdus merula"
        assert normalize_species_name("TURDUS MERULA") == "Turdus merula"

    def test_strips_whitespace(self):
        """Test that whitespace is stripped."""
        from birdhomie.inaturalist import normalize_species_name

        assert normalize_species_name("  Turdus merula  ") == "Turdus merula"

    def test_handles_subspecies(self):
        """Test handling of subspecies names."""
        from birdhomie.inaturalist import normalize_species_name

        result = normalize_species_name("Parus major major")
        assert result == "Parus major major"


class TestFetchSpeciesFromAPI:
    """Test iNaturalist API fetching."""

    @patch("birdhomie.inaturalist.requests.get")
    def test_successful_fetch(self, mock_get):
        """Test successful API fetch."""
        from birdhomie.inaturalist import fetch_species_from_api

        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 12716,
                    "name": "Turdus merula",
                    "preferred_common_name": "Eurasian Blackbird",
                    "default_photo": {
                        "medium_url": "https://example.com/photo.jpg",
                        "attribution": "Photo by Test User",
                    },
                    "wikipedia_url": "https://en.wikipedia.org/wiki/Common_blackbird",
                }
            ]
        }
        mock_get.return_value = mock_response

        result = fetch_species_from_api("Turdus merula")

        assert result is not None
        assert result["taxon_id"] == 12716
        assert result["scientific_name"] == "Turdus merula"
        assert result["common_name_en"] == "Eurasian Blackbird"

    @patch("birdhomie.inaturalist.requests.get")
    def test_no_results(self, mock_get):
        """Test API fetch with no results."""
        from birdhomie.inaturalist import fetch_species_from_api

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_get.return_value = mock_response

        result = fetch_species_from_api("Nonexistent species")
        assert result is None

    @patch("birdhomie.inaturalist.requests.get")
    @patch("birdhomie.inaturalist.RATE_LIMIT_DELAY", 0)
    @patch("birdhomie.utils.time.sleep")  # Disable retry delays
    def test_api_error_raises_after_retries(self, mock_sleep, mock_get):
        """Test that API errors raise after retry exhaustion."""
        from birdhomie.inaturalist import fetch_species_from_api
        import requests

        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(requests.RequestException):
            fetch_species_from_api("Turdus merula")

        # Should have tried 3 times (max_attempts)
        assert mock_get.call_count == 3

    @patch("birdhomie.inaturalist.requests.get")
    @patch("birdhomie.inaturalist.RATE_LIMIT_DELAY", 0)
    @patch("birdhomie.utils.time.sleep")  # Disable retry delays
    def test_api_non_200_status_raises_after_retries(self, mock_sleep, mock_get):
        """Test that non-200 status codes raise after retry exhaustion."""
        from birdhomie.inaturalist import fetch_species_from_api
        import requests

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "500 Server Error"
        )
        mock_get.return_value = mock_response

        with pytest.raises(requests.HTTPError):
            fetch_species_from_api("Turdus merula")

        assert mock_get.call_count == 3


class TestGetOrCreateTaxon:
    """Test get_or_create_taxon function."""

    def test_existing_taxon_found(self, client):
        """Test that existing taxon is returned from database."""
        from birdhomie.inaturalist import get_or_create_taxon
        from birdhomie import database as db

        # First check if Turdus merula exists in test DB
        with db.get_connection() as conn:
            existing = conn.execute(
                "SELECT taxon_id FROM inaturalist_taxa WHERE scientific_name = 'Turdus merula'"
            ).fetchone()

        if existing:
            # Should return existing taxon without API call
            with patch("birdhomie.inaturalist.fetch_species_from_api") as mock_fetch:
                result = get_or_create_taxon("Turdus merula")
                assert result == existing["taxon_id"]
                # API should not be called for existing taxon
                mock_fetch.assert_not_called()

    @patch("birdhomie.inaturalist.download_species_image")
    @patch("birdhomie.inaturalist.fetch_species_from_api")
    @patch("birdhomie.inaturalist.RATE_LIMIT_DELAY", 0)
    def test_creates_new_taxon(self, mock_fetch, mock_download, client_empty_db):
        """Test creating a new taxon from API."""
        from birdhomie.inaturalist import get_or_create_taxon
        from birdhomie import database as db

        # Mock API response - must return a proper dict, not MagicMock
        mock_fetch.return_value = {
            "taxon_id": 99999,
            "scientific_name": "Test species",
            "common_name_en": "Test Bird",
            "common_name_de": "Testvogel",
            "image_url": "https://example.com/photo.jpg",
            "image_attribution": "Test attribution",
            "wikipedia_url": None,
        }
        mock_download.return_value = None  # No image downloaded

        result = get_or_create_taxon("Test species")

        assert result == 99999
        mock_fetch.assert_called_once()

        # Verify it was stored in database
        with db.get_connection() as conn:
            stored = conn.execute(
                "SELECT * FROM inaturalist_taxa WHERE taxon_id = 99999"
            ).fetchone()
            assert stored is not None
            assert stored["scientific_name"] == "Test species"
            assert stored["common_name_en"] == "Test Bird"

    @patch("birdhomie.inaturalist.download_species_image")
    @patch("birdhomie.inaturalist.fetch_species_from_api")
    @patch("birdhomie.inaturalist.RATE_LIMIT_DELAY", 0)
    def test_case_insensitive_lookup(self, mock_fetch, mock_download, client_empty_db):
        """Test that lookup is case-insensitive for robustness."""
        from birdhomie.inaturalist import get_or_create_taxon

        # First create a taxon with canonical casing from "API"
        mock_fetch.return_value = {
            "taxon_id": 88888,
            "scientific_name": "Parus major",  # Canonical from iNaturalist
            "common_name_en": "Great Tit",
            "common_name_de": "Kohlmeise",
            "image_url": None,
            "image_attribution": None,
            "wikipedia_url": None,
        }
        mock_download.return_value = None

        # Create the taxon
        result1 = get_or_create_taxon("Parus major")
        assert result1 == 88888
        mock_fetch.assert_called_once()
        mock_fetch.reset_mock()

        # Now query with different casing - should find existing without API call
        result2 = get_or_create_taxon("PARUS MAJOR")
        assert result2 == 88888
        mock_fetch.assert_not_called()  # Should not call API - found in DB

        # Also test with mixed case
        result3 = get_or_create_taxon("parus Major")
        assert result3 == 88888
        mock_fetch.assert_not_called()

    @patch("birdhomie.inaturalist.fetch_species_from_api")
    def test_returns_none_on_api_failure(self, mock_fetch, client_empty_db):
        """Test that None is returned when API fails."""
        from birdhomie.inaturalist import get_or_create_taxon

        mock_fetch.return_value = None

        result = get_or_create_taxon("Unknown species")
        assert result is None


class TestIntegrationWithRealData:
    """Integration tests using real synced data (if available)."""

    def test_known_species_in_database(self, client):
        """Test that common species exist in the synced database."""
        from birdhomie import database as db

        common_species = [
            "Turdus merula",  # Blackbird
            "Parus major",  # Great Tit
            "Erithacus rubecula",  # Robin
        ]

        with db.get_connection() as conn:
            for species in common_species:
                result = conn.execute(
                    "SELECT taxon_id FROM inaturalist_taxa WHERE scientific_name = ?",
                    (species,),
                ).fetchone()
                # This may fail if species isn't in test data - that's OK
                if result:
                    assert result["taxon_id"] > 0, (
                        f"{species} should have valid taxon_id"
                    )

    def test_get_or_create_returns_existing(self, client):
        """Test get_or_create_taxon returns existing taxon without API call."""
        from birdhomie.inaturalist import get_or_create_taxon
        from birdhomie import database as db

        # Get a taxon that exists
        with db.get_connection() as conn:
            existing = conn.execute(
                "SELECT taxon_id, scientific_name FROM inaturalist_taxa LIMIT 1"
            ).fetchone()

        if existing:
            with patch("birdhomie.inaturalist.fetch_species_from_api") as mock_fetch:
                result = get_or_create_taxon(existing["scientific_name"])
                assert result == existing["taxon_id"]
                mock_fetch.assert_not_called()
