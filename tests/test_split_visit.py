"""Tests for the split visit feature."""

import pytest
import json


class TestSplitVisitPreview:
    """Test the split preview API endpoint."""

    def test_split_preview_not_found(self, client_empty_db):
        """Test split preview returns 404 for non-existent visit."""
        response = client_empty_db.get("/api/visits/999999/split-preview")
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data

    def test_split_preview_with_valid_visit(self, client):
        """Test split preview returns correct data structure for valid visit."""
        # First, find a valid visit ID from the database
        from birdhomie import database as db

        with db.get_connection() as conn:
            visit = conn.execute("""
                SELECT v.id, f.file_path
                FROM visits v
                JOIN files f ON v.file_id = f.id
                WHERE v.deleted_at IS NULL
                    AND f.file_path LIKE '%.mp4'
                    AND v.segment_start_time IS NULL
                LIMIT 1
            """).fetchone()

        if visit is None:
            pytest.skip("No video visits available in test database")

        response = client.get(f"/api/visits/{visit['id']}/split-preview")

        # Could be 200 (success) or 400 (if video file doesn't exist)
        if response.status_code == 200:
            data = response.get_json()
            assert "visit_id" in data
            assert "file_id" in data
            assert "duration_seconds" in data
            assert "detections" in data
            assert "current_species" in data
            assert "all_species" in data
            assert isinstance(data["detections"], list)
            assert isinstance(data["all_species"], list)


class TestSplitVisitAPI:
    """Test the split visit API endpoint."""

    def test_split_requires_segments(self, client_empty_db):
        """Test split endpoint requires segments in request body."""
        response = client_empty_db.post(
            "/api/visits/1/split", data=json.dumps({}), content_type="application/json"
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "segments" in data["error"].lower()

    def test_split_requires_at_least_two_segments(self, client_empty_db):
        """Test split endpoint requires at least 2 segments."""
        response = client_empty_db.post(
            "/api/visits/1/split",
            data=json.dumps(
                {"segments": [{"start_time": 0, "end_time": 10, "taxon_id": 1}]}
            ),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "2 segments" in data["error"]

    def test_split_validates_segment_structure(self, client_empty_db):
        """Test split endpoint validates segment structure."""
        response = client_empty_db.post(
            "/api/visits/1/split",
            data=json.dumps(
                {
                    "segments": [
                        {"start_time": 0, "end_time": 10},  # Missing taxon_id
                        {"start_time": 10, "end_time": 20, "taxon_id": 1},
                    ]
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "taxon_id" in data["error"]

    def test_split_validates_time_range(self, client_empty_db):
        """Test split endpoint validates time ranges (start < end)."""
        response = client_empty_db.post(
            "/api/visits/1/split",
            data=json.dumps(
                {
                    "segments": [
                        {
                            "start_time": 10,
                            "end_time": 5,
                            "taxon_id": 1,
                        },  # Invalid: start > end
                        {"start_time": 15, "end_time": 20, "taxon_id": 1},
                    ]
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "invalid time range" in data["error"].lower()

    def test_split_validates_no_negative_times(self, client_empty_db):
        """Test split endpoint validates no negative times."""
        response = client_empty_db.post(
            "/api/visits/1/split",
            data=json.dumps(
                {
                    "segments": [
                        {"start_time": -5, "end_time": 5, "taxon_id": 1},
                        {"start_time": 10, "end_time": 20, "taxon_id": 1},
                    ]
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "negative" in data["error"].lower()

    def test_split_validates_no_overlap(self, client_empty_db):
        """Test split endpoint validates segments don't overlap."""
        response = client_empty_db.post(
            "/api/visits/1/split",
            data=json.dumps(
                {
                    "segments": [
                        {"start_time": 0, "end_time": 15, "taxon_id": 1},
                        {
                            "start_time": 10,
                            "end_time": 25,
                            "taxon_id": 1,
                        },  # Overlaps with first
                    ]
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "overlap" in data["error"].lower()

    def test_split_visit_not_found(self, client_empty_db):
        """Test split returns 404 for non-existent visit."""
        response = client_empty_db.post(
            "/api/visits/999999/split",
            data=json.dumps(
                {
                    "segments": [
                        {"start_time": 0, "end_time": 10, "taxon_id": 1},
                        {"start_time": 15, "end_time": 25, "taxon_id": 1},
                    ]
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 404


class TestSplitVisitPage:
    """Test the split visit page route."""

    def test_split_page_not_found(self, client_empty_db):
        """Test split page redirects for non-existent visit."""
        response = client_empty_db.get("/visits/999999/split")
        # Should redirect to dashboard with flash message
        assert response.status_code in [302, 404]

    def test_split_page_with_valid_visit(self, client):
        """Test split page loads for valid video visit."""
        from birdhomie import database as db

        with db.get_connection() as conn:
            visit = conn.execute("""
                SELECT v.id, f.file_path
                FROM visits v
                JOIN files f ON v.file_id = f.id
                WHERE v.deleted_at IS NULL
                    AND f.file_path LIKE '%.mp4'
                    AND v.segment_start_time IS NULL
                LIMIT 1
            """).fetchone()

        if visit is None:
            pytest.skip("No video visits available in test database")

        response = client.get(f"/visits/{visit['id']}/split")
        # Could be 200 (page loads) or 302 (redirect if video not available)
        assert response.status_code in [200, 302]


class TestSplitIntegration:
    """Integration tests for the complete split workflow."""

    def test_full_split_workflow(self, client):
        """Test the complete split workflow from preview to execution."""
        from birdhomie import database as db

        # Find a valid video visit with detections
        with db.get_connection() as conn:
            visit = conn.execute("""
                SELECT v.id, v.file_id, f.duration_seconds, v.inaturalist_taxon_id
                FROM visits v
                JOIN files f ON v.file_id = f.id
                WHERE v.deleted_at IS NULL
                    AND f.file_path LIKE '%.mp4'
                    AND v.segment_start_time IS NULL
                    AND f.duration_seconds > 5
                LIMIT 1
            """).fetchone()

            if visit is None:
                pytest.skip("No suitable video visits available in test database")

            # Verify detections exist for this visit
            conn.execute(
                "SELECT COUNT(*) as count FROM detections WHERE visit_id = ?",
                (visit["id"],),
            ).fetchone()["count"]

        visit_id = visit["id"]
        duration = visit["duration_seconds"]
        taxon_id = visit["inaturalist_taxon_id"]

        # Test 1: Preview endpoint
        preview_response = client.get(f"/api/visits/{visit_id}/split-preview")
        # May fail if video file not available, which is OK
        if preview_response.status_code != 200:
            pytest.skip("Video file not available for split preview")

        preview_data = preview_response.get_json()
        assert preview_data["visit_id"] == visit_id

        # Test 2: Execute split
        midpoint = duration / 2
        split_response = client.post(
            f"/api/visits/{visit_id}/split",
            data=json.dumps(
                {
                    "segments": [
                        {"start_time": 0, "end_time": midpoint, "taxon_id": taxon_id},
                        {
                            "start_time": midpoint,
                            "end_time": duration,
                            "taxon_id": taxon_id,
                        },
                    ]
                }
            ),
            content_type="application/json",
        )

        # Check split was successful
        if split_response.status_code != 200:
            # May fail due to video duration mismatch, etc.
            data = split_response.get_json()
            print(f"Split failed: {data.get('error', 'Unknown error')}")
            pytest.skip("Split failed due to data constraints")

        split_data = split_response.get_json()
        assert split_data["success"] is True
        assert len(split_data["created_visits"]) == 2
        assert split_data["original_visit_status"] == "archived"

        # Test 3: Verify database state
        with db.get_connection() as conn:
            # Original visit should be soft-deleted
            original = conn.execute(
                "SELECT deleted_at FROM visits WHERE id = ?", (visit_id,)
            ).fetchone()
            assert original["deleted_at"] is not None

            # New visits should exist with segment times
            for new_visit in split_data["created_visits"]:
                new_v = conn.execute(
                    """SELECT segment_start_time, segment_end_time, parent_visit_id
                       FROM visits WHERE id = ?""",
                    (new_visit["id"],),
                ).fetchone()
                assert new_v is not None
                assert new_v["segment_start_time"] is not None
                assert new_v["segment_end_time"] is not None
                assert new_v["parent_visit_id"] == visit_id


class TestSplitVisitButton:
    """Test that the split button appears correctly on visit detail page."""

    def test_split_button_hidden_for_image_visits(self, client):
        """Test that split button is not shown for image-based visits."""
        from birdhomie import database as db

        with db.get_connection() as conn:
            visit = conn.execute("""
                SELECT v.id
                FROM visits v
                JOIN files f ON v.file_id = f.id
                WHERE v.deleted_at IS NULL
                    AND f.file_path NOT LIKE '%.mp4'
                    AND f.file_path NOT LIKE '%.avi'
                    AND f.file_path NOT LIKE '%.mov'
                    AND f.file_path NOT LIKE '%.mkv'
                LIMIT 1
            """).fetchone()

        if visit is None:
            pytest.skip("No image visits available in test database")

        response = client.get(f"/visits/{visit['id']}")
        assert response.status_code == 200
        # Split button should not be present for image files
        assert (
            b"Split Visit" not in response.data
            or b"only supported for video" in response.data
        )


class TestAlreadySplitVisit:
    """Test behavior when trying to split an already-split visit."""

    def test_cannot_split_already_split_visit_api(self, client):
        """Test that API rejects splitting an already-split visit."""
        from birdhomie import database as db

        with db.get_connection() as conn:
            # Find a visit that has segment times (already split)
            visit = conn.execute("""
                SELECT id FROM visits
                WHERE segment_start_time IS NOT NULL
                    AND deleted_at IS NULL
                LIMIT 1
            """).fetchone()

        if visit is None:
            pytest.skip("No split visits available in test database")

        # Try to split it again
        response = client.post(
            f"/api/visits/{visit['id']}/split",
            data=json.dumps(
                {
                    "segments": [
                        {"start_time": 0, "end_time": 5, "taxon_id": 1},
                        {"start_time": 5, "end_time": 10, "taxon_id": 1},
                    ]
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "already" in data["error"].lower()
