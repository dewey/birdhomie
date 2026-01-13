"""Tests for external identifiers feature."""

import pytest
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from birdhomie.app import (
    build_external_url,
    get_source_icon,
    get_source_label,
    get_source_description,
    parse_external_identifier,
)


class TestBuildExternalUrl:
    """Tests for build_external_url function."""

    def test_inaturalist_url(self):
        """Test building iNaturalist URL."""
        url = build_external_url("inaturalist", "13094")
        assert url == "https://www.inaturalist.org/taxa/13094"

    def test_wikidata_url(self):
        """Test building Wikidata URL."""
        url = build_external_url("wikidata", "Q25394")
        assert url == "https://www.wikidata.org/wiki/Q25394"

    def test_ebird_url(self):
        """Test building eBird URL."""
        url = build_external_url("ebird", "gretit1")
        assert url == "https://ebird.org/species/gretit1"

    def test_wikipedia_url_passthrough(self):
        """Test that Wikipedia URLs are returned as-is."""
        full_url = "https://en.wikipedia.org/wiki/Great_tit"
        url = build_external_url("wikipedia", full_url)
        assert url == full_url

    def test_unknown_source(self):
        """Test unknown source returns identifier as-is."""
        url = build_external_url("unknown", "some_id")
        assert url == "some_id"


class TestGetSourceIcon:
    """Tests for get_source_icon function."""

    def test_inaturalist_icon(self):
        """Test iNaturalist icon."""
        assert get_source_icon("inaturalist") == "bi-binoculars-fill"

    def test_wikipedia_icon(self):
        """Test Wikipedia icon."""
        assert get_source_icon("wikipedia") == "bi-wikipedia"

    def test_wikidata_icon(self):
        """Test Wikidata icon."""
        assert get_source_icon("wikidata") == "bi-database"

    def test_ebird_icon(self):
        """Test eBird icon."""
        assert get_source_icon("ebird") == "bi-egg"

    def test_unknown_source_icon(self):
        """Test unknown source returns default icon."""
        assert get_source_icon("unknown") == "bi-link-45deg"


class TestGetSourceLabel:
    """Tests for get_source_label function."""

    def test_basic_labels(self):
        """Test basic labels without language code."""
        # These will return the _() function result which in tests might just be the string
        label = get_source_label("inaturalist")
        assert "iNaturalist" in label or label == "iNaturalist"

    def test_label_with_language_code(self):
        """Test label with language code appended."""
        label = get_source_label("wikipedia", "en")
        assert "(EN)" in label

    def test_label_with_de_language_code(self):
        """Test label with German language code."""
        label = get_source_label("wikipedia", "de")
        assert "(DE)" in label


class TestParseExternalIdentifier:
    """Tests for parse_external_identifier function."""

    def test_parse_ebird_url(self):
        """Test parsing eBird URL."""
        result = parse_external_identifier("ebird", "https://ebird.org/species/gretit1")
        assert result == "gretit1"

    def test_parse_ebird_identifier_passthrough(self):
        """Test that non-URL identifier is passed through."""
        result = parse_external_identifier("ebird", "gretit1")
        assert result == "gretit1"

    def test_parse_wikidata_url(self):
        """Test parsing Wikidata URL."""
        result = parse_external_identifier(
            "wikidata", "https://www.wikidata.org/wiki/Q25394"
        )
        assert result == "Q25394"

    def test_parse_inaturalist_url(self):
        """Test parsing iNaturalist URL."""
        result = parse_external_identifier(
            "inaturalist", "https://www.inaturalist.org/taxa/13094"
        )
        assert result == "13094"

    def test_parse_wikipedia_url_passthrough(self):
        """Test that Wikipedia URL is passed through as-is."""
        url = "https://en.wikipedia.org/wiki/Great_tit"
        result = parse_external_identifier("wikipedia", url)
        assert result == url

    def test_parse_invalid_ebird_url(self):
        """Test that invalid URL returns None."""
        result = parse_external_identifier("ebird", "https://example.com/invalid")
        assert result is None

    def test_parse_plain_identifier_no_url(self):
        """Test that non-URL identifiers are passed through."""
        result = parse_external_identifier("wikidata", "Q12345")
        assert result == "Q12345"


class TestGetSourceDescription:
    """Tests for get_source_description function."""

    def test_inaturalist_description(self):
        """Test iNaturalist description."""
        desc = get_source_description("inaturalist")
        # Check it's not empty
        assert desc

    def test_unknown_source_description(self):
        """Test unknown source returns empty string."""
        desc = get_source_description("unknown")
        assert desc == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
