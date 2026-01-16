"""Tests for data access repositories."""

from datetime import datetime
from pathlib import Path
from birdhomie.repositories import FileRepository, VisitRepository


class TestFileRepository:
    """Test file repository operations."""

    def test_create_and_get_by_hash(self, client_empty_db):
        """Test creating a file and retrieving by hash."""
        repo = FileRepository()

        file_path = Path("/test/video.mp4")
        file_hash = "abc123"
        event_start = datetime(2024, 1, 1, 12, 0, 0)

        file_id = repo.create(file_path, file_hash, event_start)

        assert file_id is not None
        assert file_id > 0

        # Retrieve by hash
        retrieved = repo.get_by_hash(file_hash)

        assert retrieved is not None
        assert retrieved["id"] == file_id
        assert retrieved["status"] == "processing"

    def test_get_by_hash_nonexistent(self, client_empty_db):
        """Test getting a nonexistent file returns None."""
        repo = FileRepository()

        result = repo.get_by_hash("nonexistent_hash")

        assert result is None

    def test_mark_success(self, client_empty_db):
        """Test marking a file as successfully processed."""
        repo = FileRepository()

        file_id = repo.create(Path("/test/video.mp4"), "hash123", datetime.now())

        repo.mark_success(file_id, 15.5, "output/123")

        # Verify status
        retrieved = repo.get_by_hash("hash123")
        assert retrieved["status"] == "success"

    def test_mark_failed(self, client_empty_db):
        """Test marking a file as failed."""
        repo = FileRepository()

        file_id = repo.create(Path("/test/video.mp4"), "hash456", datetime.now())

        repo.mark_failed(file_id, "Processing error occurred")

        # Verify status
        retrieved = repo.get_by_hash("hash456")
        assert retrieved["status"] == "failed"

    def test_mark_processing(self, client_empty_db):
        """Test marking a file as processing."""
        repo = FileRepository()

        file_id = repo.create(Path("/test/video.mp4"), "hash789", datetime.now())

        repo.mark_processing(file_id)

        # Verify status
        retrieved = repo.get_by_hash("hash789")
        assert retrieved["status"] == "processing"

    def test_get_pending_files(self, client_empty_db):
        """Test retrieving pending files."""
        from birdhomie import database as db

        repo = FileRepository()

        # Create some files with different statuses
        with db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO files (file_path, file_hash, event_start, status)
                VALUES
                    ('/test/pending1.mp4', 'hash1', datetime('now'), 'pending'),
                    ('/test/pending2.mp4', 'hash2', datetime('now'), 'pending'),
                    ('/test/success.mp4', 'hash3', datetime('now'), 'success')
            """
            )

        pending = repo.get_pending_files()

        assert len(pending) == 2
        paths = [p["file_path"] for p in pending]
        assert "/test/pending1.mp4" in paths
        assert "/test/pending2.mp4" in paths
        assert "/test/success.mp4" not in paths


class TestVisitRepository:
    """Test visit repository operations."""

    def setup_test_file(self, client_empty_db):
        """Helper to create a test file."""
        from birdhomie import database as db

        with db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO files (file_path, file_hash, event_start, status)
                VALUES ('/test/video.mp4', 'testhash', datetime('now'), 'processing')
            """
            )
            file_id = cursor.lastrowid

            # Also create a test taxon
            cursor = conn.execute(
                """
                INSERT INTO inaturalist_taxa (taxon_id, scientific_name)
                VALUES (12345, 'Parus major')
            """
            )

        return file_id, 12345

    def test_create_visit(self, client_empty_db):
        """Test creating a visit."""
        file_id, taxon_id = self.setup_test_file(client_empty_db)
        repo = VisitRepository()

        visit_id = repo.create(file_id, taxon_id, 0.92, 5)

        assert visit_id is not None
        assert visit_id > 0

    def test_get_by_file_and_taxon(self, client_empty_db):
        """Test retrieving visit by file and taxon."""
        file_id, taxon_id = self.setup_test_file(client_empty_db)
        repo = VisitRepository()

        # Create a visit
        visit_id = repo.create(file_id, taxon_id, 0.92, 5)

        # Retrieve it
        retrieved = repo.get_by_file_and_taxon(file_id, taxon_id)

        assert retrieved is not None
        assert retrieved["id"] == visit_id

    def test_get_by_file_and_taxon_nonexistent(self, client_empty_db):
        """Test getting nonexistent visit returns None."""
        repo = VisitRepository()

        result = repo.get_by_file_and_taxon(99999, 99999)

        assert result is None

    def test_update_visit(self, client_empty_db):
        """Test updating a visit."""
        file_id, taxon_id = self.setup_test_file(client_empty_db)
        repo = VisitRepository()

        # Create a visit
        visit_id = repo.create(file_id, taxon_id, 0.92, 5)

        # Update it
        repo.update(visit_id, 0.95, 10)

        # Verify update (need to query database directly)
        from birdhomie import database as db

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT species_confidence, detection_count FROM visits WHERE id = ?",
                (visit_id,),
            ).fetchone()

        assert abs(row["species_confidence"] - 0.95) < 0.001
        assert row["detection_count"] == 10

    def test_add_detection(self, client_empty_db):
        """Test adding a detection to a visit."""
        file_id, taxon_id = self.setup_test_file(client_empty_db)
        repo = VisitRepository()

        visit_id = repo.create(file_id, taxon_id, 0.92, 1)

        detection = {
            "frame_number": 100,
            "frame_timestamp": 2.0,
            "detection_confidence": 0.88,
            "species_confidence": 0.92,
            "bbox": (10, 20, 100, 200),
            "crop_path": "output/1/crops/frame_000100_det00.jpg",
            "is_edge": False,
        }

        detection_id = repo.add_detection(visit_id, detection)

        assert detection_id is not None
        assert detection_id > 0

        # Verify detection was added
        from birdhomie import database as db

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM detections WHERE id = ?", (detection_id,)
            ).fetchone()

        assert row is not None
        assert row["visit_id"] == visit_id
        assert row["frame_number"] == 100
        assert abs(row["frame_timestamp"] - 2.0) < 0.001

    def test_delete_detections(self, client_empty_db):
        """Test deleting all detections for a visit."""
        file_id, taxon_id = self.setup_test_file(client_empty_db)
        repo = VisitRepository()

        visit_id = repo.create(file_id, taxon_id, 0.92, 3)

        # Add some detections
        for i in range(3):
            detection = {
                "frame_number": i * 10,
                "frame_timestamp": float(i),
                "detection_confidence": 0.88,
                "species_confidence": 0.92,
                "bbox": (10, 20, 100, 200),
                "crop_path": f"output/1/crops/frame_{i:06d}_det00.jpg",
                "is_edge": False,
            }
            repo.add_detection(visit_id, detection)

        # Delete all detections
        repo.delete_detections(visit_id)

        # Verify they're gone
        from birdhomie import database as db

        with db.get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) as cnt FROM detections WHERE visit_id = ?",
                (visit_id,),
            ).fetchone()["cnt"]

        assert count == 0

    def test_update_cover_detection(self, client_empty_db):
        """Test updating cover detection IDs."""
        file_id, taxon_id = self.setup_test_file(client_empty_db)
        repo = VisitRepository()

        visit_id = repo.create(file_id, taxon_id, 0.92, 1)

        detection = {
            "frame_number": 100,
            "frame_timestamp": 2.0,
            "detection_confidence": 0.88,
            "species_confidence": 0.92,
            "bbox": (10, 20, 100, 200),
            "crop_path": "output/1/crops/frame_000100_det00.jpg",
            "is_edge": False,
        }

        detection_id = repo.add_detection(visit_id, detection)

        # Update cover detection
        repo.update_cover_detection(visit_id, detection_id, detection_id)

        # Verify
        from birdhomie import database as db

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT best_detection_id, cover_detection_id FROM visits WHERE id = ?",
                (visit_id,),
            ).fetchone()

        assert row["best_detection_id"] == detection_id
        assert row["cover_detection_id"] == detection_id
