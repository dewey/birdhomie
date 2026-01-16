"""Integration tests for FileProcessor."""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from datetime import datetime
from birdhomie.processor import FileProcessor
from birdhomie.config import Config


class TestFileProcessorIntegration:
    """Integration tests for the full processing pipeline."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        config = MagicMock(spec=Config)
        config.min_detection_confidence = 0.8
        config.min_species_confidence = 0.85
        config.frame_skip = 5
        config.processor_workers = 1
        return config

    def test_processor_initialization(self, mock_config):
        """Test that processor initializes all components."""
        processor = FileProcessor(mock_config)

        assert processor.config == mock_config
        assert processor.detector is not None
        assert processor.classifier is not None
        assert processor.file_repo is not None
        assert processor.visit_repo is not None
        assert processor.frame_extractor is not None
        assert processor.annotator is not None
        assert processor.visit_grouper is not None

    def test_processor_with_mocked_components(self, mock_config, client_empty_db):
        """Test processor with mocked components."""
        # First create the taxon in the database
        from birdhomie import database as db

        with db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO inaturalist_taxa (taxon_id, scientific_name, common_name_en)
                VALUES (12345, 'Parus major', 'Great Tit')
            """
            )

        # Create mocked components
        mock_detector = MagicMock()
        mock_classifier = MagicMock()
        mock_frame_extractor = MagicMock()
        mock_annotator = MagicMock()

        # Setup frame extractor to return video info
        mock_frame_extractor.get_video_info.return_value = {
            "fps": 30.0,
            "width": 640,
            "height": 480,
            "total_frames": 100,
        }

        # Setup frame extractor to yield some frames
        import numpy as np

        frames = [
            (0, np.zeros((480, 640, 3), dtype=np.uint8)),
            (5, np.zeros((480, 640, 3), dtype=np.uint8)),
        ]
        mock_frame_extractor.extract_frames.return_value = iter(frames)

        # Setup detector to return detections
        mock_detector.detect_birds.return_value = [
            {"bbox": (100, 100, 200, 200), "confidence": 0.9, "class_id": 14}
        ]
        mock_detector.is_edge_detection.return_value = False

        # Setup classifier to return species
        mock_classifier.classify_from_array.return_value = ("Parus major", 0.92)

        # Create processor with mocked components
        processor = FileProcessor(
            mock_config,
            detector=mock_detector,
            classifier=mock_classifier,
            frame_extractor=mock_frame_extractor,
            annotator=mock_annotator,
        )

        # Create a test file path (won't actually read it due to mocking)
        test_file = Path(__file__)  # Use this test file itself

        # Mock get_or_create_taxon to return the taxon we created
        with patch("birdhomie.processor.get_or_create_taxon", return_value=12345):
            with patch("birdhomie.processor.fetch_and_store_wikipedia_pages"):
                result = processor.process_file(test_file)

        # Verify processing succeeded
        assert result is True

        # Verify components were called
        assert mock_frame_extractor.get_video_info.called
        assert mock_frame_extractor.extract_frames.called
        assert mock_detector.detect_birds.called
        assert mock_classifier.classify_from_array.called
        assert mock_annotator.create_annotated_video.called

    def test_process_pending_files_with_mock_repo(self, mock_config, client_empty_db):
        """Test processing pending files."""
        from birdhomie.repositories import FileRepository

        # Create some pending files in the database
        repo = FileRepository()

        # Create pending file records (using paths that won't exist)
        repo.create(Path("/fake/video1.mp4"), "hash1", datetime.now())
        repo.create(Path("/fake/video2.mp4"), "hash2", datetime.now())

        # Create processor with mocked process_file
        processor = FileProcessor(mock_config)

        with patch.object(processor, "process_file", return_value=False):
            count = processor.process_pending_files()

        # Should have found 2 pending files (even though they don't exist)
        # Both will be logged as not found, so count should be 0
        assert count == 0

    def test_file_already_processed(self, mock_config, client_empty_db):
        """Test that already-processed files are skipped."""
        from birdhomie.repositories import FileRepository
        import hashlib

        repo = FileRepository()

        # Create a file that's already successfully processed
        file_path = Path(__file__)

        # Calculate actual hash to avoid conflicts
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        file_hash = sha256.hexdigest()

        file_id = repo.create(file_path, file_hash, datetime.now())
        repo.mark_success(file_id, 10.0, "output/123")

        processor = FileProcessor(mock_config)

        # Try to process again - should skip
        result = processor.process_file(file_path)

        assert result is False  # Returns False when already processed

    def test_file_processing_error_handling(self, mock_config, client_empty_db):
        """Test that processing errors are handled gracefully."""
        mock_frame_extractor = MagicMock()

        # Make frame extractor raise an error
        mock_frame_extractor.get_video_info.side_effect = Exception("Video read error")

        processor = FileProcessor(mock_config, frame_extractor=mock_frame_extractor)

        test_file = Path(__file__)

        result = processor.process_file(test_file)

        # Should return False on error
        assert result is False

        # Verify file was marked as failed
        from birdhomie.repositories import FileRepository

        repo = FileRepository()
        # Calculate the hash to look up the file
        import hashlib

        sha256 = hashlib.sha256()
        with open(test_file, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        file_hash = sha256.hexdigest()

        file_record = repo.get_by_hash(file_hash)
        assert file_record["status"] == "failed"

    def test_visit_creation_integration(self, mock_config, client_empty_db):
        """Test that visits are created from detections."""
        # First create the taxon in the database
        from birdhomie import database as db

        with db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO inaturalist_taxa (taxon_id, scientific_name, common_name_en)
                VALUES (12345, 'Parus major', 'Great Tit')
            """
            )

        mock_frame_extractor = MagicMock()
        mock_detector = MagicMock()
        mock_classifier = MagicMock()
        mock_annotator = MagicMock()

        # Setup mocks
        mock_frame_extractor.get_video_info.return_value = {
            "fps": 30.0,
            "width": 640,
            "height": 480,
            "total_frames": 10,
        }

        import numpy as np

        mock_frame_extractor.extract_frames.return_value = iter(
            [(0, np.zeros((480, 640, 3), dtype=np.uint8))]
        )

        # Return multiple detections of the same species
        mock_detector.detect_birds.return_value = [
            {"bbox": (100, 100, 200, 200), "confidence": 0.9, "class_id": 14},
            {"bbox": (300, 300, 400, 400), "confidence": 0.85, "class_id": 14},
        ]
        mock_detector.is_edge_detection.return_value = False

        mock_classifier.classify_from_array.return_value = ("Parus major", 0.92)

        processor = FileProcessor(
            mock_config,
            detector=mock_detector,
            classifier=mock_classifier,
            frame_extractor=mock_frame_extractor,
            annotator=mock_annotator,
        )

        test_file = Path(__file__)

        with patch("birdhomie.processor.get_or_create_taxon", return_value=12345):
            with patch("birdhomie.processor.fetch_and_store_wikipedia_pages"):
                result = processor.process_file(test_file)

        assert result is True

        # Verify visit was created

        with db.get_connection() as conn:
            visits = conn.execute("SELECT * FROM visits").fetchall()
            assert len(visits) == 1

            # Verify detections were created
            detections = conn.execute("SELECT * FROM detections").fetchall()
            assert len(detections) == 2  # 2 detections of same species
