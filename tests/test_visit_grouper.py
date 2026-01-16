"""Tests for visit grouping logic."""

from birdhomie.visit_grouper import VisitGrouper


class TestVisitGrouper:
    """Test visit grouping logic."""

    def test_group_detections_by_species(self):
        """Test that detections are grouped by species."""
        grouper = VisitGrouper(min_species_confidence=0.85)

        detections = [
            {
                "species_name": "Parus major",
                "species_confidence": 0.9,
                "detection_confidence": 0.85,
            },
            {
                "species_name": "Parus major",
                "species_confidence": 0.92,
                "detection_confidence": 0.88,
            },
            {
                "species_name": "Turdus merula",
                "species_confidence": 0.87,
                "detection_confidence": 0.90,
            },
        ]

        groups = grouper.group_detections(detections)

        assert len(groups) == 2
        assert "Parus major" in groups
        assert "Turdus merula" in groups
        assert len(groups["Parus major"]) == 2
        assert len(groups["Turdus merula"]) == 1

    def test_filters_low_confidence_detections(self):
        """Test that low confidence detections are filtered out."""
        grouper = VisitGrouper(min_species_confidence=0.85)

        detections = [
            {
                "species_name": "Parus major",
                "species_confidence": 0.9,
                "detection_confidence": 0.85,
            },
            {
                "species_name": "Parus major",
                "species_confidence": 0.5,  # Too low
                "detection_confidence": 0.88,
            },
            {
                "species_name": "Turdus merula",
                "species_confidence": 0.7,  # Too low
                "detection_confidence": 0.90,
            },
        ]

        groups = grouper.group_detections(detections)

        # Only one high-confidence detection should be included
        assert len(groups) == 1
        assert "Parus major" in groups
        assert len(groups["Parus major"]) == 1

    def test_filters_none_confidence(self):
        """Test that detections with None confidence are filtered."""
        grouper = VisitGrouper(min_species_confidence=0.85)

        detections = [
            {
                "species_name": "Parus major",
                "species_confidence": None,  # Edge detection
                "detection_confidence": 0.85,
            },
            {
                "species_name": "Turdus merula",
                "species_confidence": 0.9,
                "detection_confidence": 0.90,
            },
        ]

        groups = grouper.group_detections(detections)

        # Only the valid detection should be included
        assert len(groups) == 1
        assert "Turdus merula" in groups

    def test_empty_detections(self):
        """Test handling of empty detection list."""
        grouper = VisitGrouper(min_species_confidence=0.85)

        groups = grouper.group_detections([])

        assert len(groups) == 0

    def test_no_high_confidence_detections(self):
        """Test when no detections pass the confidence threshold."""
        grouper = VisitGrouper(min_species_confidence=0.85)

        detections = [
            {
                "species_name": "Parus major",
                "species_confidence": 0.5,
                "detection_confidence": 0.85,
                "is_edge": False,
            },
            {
                "species_name": "Turdus merula",
                "species_confidence": 0.7,
                "detection_confidence": 0.90,
                "is_edge": False,
            },
        ]

        groups = grouper.group_detections(detections)

        assert len(groups) == 0

    def test_get_visit_summary_finds_best_detection(self):
        """Test that visit summary identifies best detection."""
        grouper = VisitGrouper()

        detections = [
            {"detection_confidence": 0.85, "species_confidence": 0.9},
            {"detection_confidence": 0.95, "species_confidence": 0.88},  # Best
            {"detection_confidence": 0.80, "species_confidence": 0.92},
        ]

        summary = grouper.get_visit_summary(detections)

        assert summary["best_detection_idx"] == 1  # Index of highest detection conf
        assert summary["detection_count"] == 3

    def test_get_visit_summary_calculates_average_confidence(self):
        """Test that visit summary calculates average species confidence."""
        grouper = VisitGrouper()

        detections = [
            {"detection_confidence": 0.85, "species_confidence": 0.9},
            {"detection_confidence": 0.88, "species_confidence": 0.8},
            {"detection_confidence": 0.90, "species_confidence": 0.7},
        ]

        summary = grouper.get_visit_summary(detections)

        expected_avg = (0.9 + 0.8 + 0.7) / 3
        assert abs(summary["avg_species_confidence"] - expected_avg) < 0.001

    def test_get_visit_summary_empty_list(self):
        """Test visit summary with empty detection list."""
        grouper = VisitGrouper()

        summary = grouper.get_visit_summary([])

        assert summary["best_detection_idx"] is None
        assert summary["avg_species_confidence"] == 0.0
        assert summary["detection_count"] == 0

    def test_custom_confidence_threshold(self):
        """Test that custom confidence threshold is respected."""
        grouper = VisitGrouper(min_species_confidence=0.95)

        detections = [
            {
                "species_name": "Parus major",
                "species_confidence": 0.9,  # Below threshold
                "detection_confidence": 0.85,
            },
            {
                "species_name": "Turdus merula",
                "species_confidence": 0.96,  # Above threshold
                "detection_confidence": 0.90,
            },
        ]

        groups = grouper.group_detections(detections)

        assert len(groups) == 1
        assert "Turdus merula" in groups
        assert "Parus major" not in groups

    def test_handles_missing_species_name(self):
        """Test that detections without species names are skipped."""
        grouper = VisitGrouper(min_species_confidence=0.85)

        detections = [
            {
                "species_name": None,  # No species name
                "species_confidence": 0.9,
                "detection_confidence": 0.85,
            },
            {
                "species_name": "Parus major",
                "species_confidence": 0.9,
                "detection_confidence": 0.88,
            },
        ]

        groups = grouper.group_detections(detections)

        assert len(groups) == 1
        assert "Parus major" in groups
        assert None not in groups
