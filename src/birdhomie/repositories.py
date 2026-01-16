"""Data access layer for database operations."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from . import database as db
from .constants import YOLO_MODEL_PATH, BIOCLIP_MODEL_NAME

logger = logging.getLogger(__name__)


class FileRepository:
    """Repository for file-related database operations."""

    def get_by_hash(self, file_hash: str) -> Optional[Dict]:
        """Get file record by hash.

        Args:
            file_hash: SHA256 hash of file

        Returns:
            File record or None
        """
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT id, status FROM files WHERE file_hash = ?",
                (file_hash,),
            ).fetchone()
            return dict(row) if row else None

    def create(self, file_path: Path, file_hash: str, event_start: datetime) -> int:
        """Create a new file record.

        Args:
            file_path: Path to file
            file_hash: SHA256 hash
            event_start: Event start timestamp

        Returns:
            File ID
        """
        with db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO files
                (file_path, file_hash, event_start, status)
                VALUES (?, ?, ?, 'processing')
            """,
                (str(file_path), file_hash, event_start),
            )
            return cursor.lastrowid

    def update_status(
        self, file_id: int, status: str, error_message: Optional[str] = None
    ):
        """Update file status.

        Args:
            file_id: File ID
            status: New status
            error_message: Optional error message
        """
        with db.get_connection() as conn:
            if error_message:
                conn.execute(
                    """
                    UPDATE files
                    SET status = ?, error_message = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (status, error_message, file_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE files
                    SET status = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (status, file_id),
                )

    def mark_processing(self, file_id: int):
        """Mark file as processing.

        Args:
            file_id: File ID
        """
        with db.get_connection() as conn:
            conn.execute(
                """
                UPDATE files
                SET status = 'processing', processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (file_id,),
            )

    def mark_success(self, file_id: int, duration_seconds: float, output_dir: str):
        """Mark file as successfully processed.

        Args:
            file_id: File ID
            duration_seconds: Video duration
            output_dir: Output directory path
        """
        with db.get_connection() as conn:
            conn.execute(
                """
                UPDATE files
                SET status = 'success',
                    duration_seconds = ?,
                    output_dir = ?,
                    processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (duration_seconds, output_dir, file_id),
            )

    def mark_failed(self, file_id: int, error_message: str):
        """Mark file as failed.

        Args:
            file_id: File ID
            error_message: Error message
        """
        self.update_status(file_id, "failed", error_message)

    def get_pending_files(self) -> List[Dict]:
        """Get all pending files.

        Returns:
            List of file records
        """
        with db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT file_path FROM files
                WHERE status = 'pending'
                ORDER BY created_at
            """
            ).fetchall()
            return [dict(row) for row in rows]


class VisitRepository:
    """Repository for visit-related database operations."""

    def get_by_file_and_taxon(self, file_id: int, taxon_id: int) -> Optional[Dict]:
        """Get visit by file and taxon.

        Args:
            file_id: File ID
            taxon_id: iNaturalist taxon ID

        Returns:
            Visit record or None
        """
        with db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM visits
                WHERE file_id = ? AND inaturalist_taxon_id = ?
            """,
                (file_id, taxon_id),
            ).fetchone()
            return dict(row) if row else None

    def create(
        self,
        file_id: int,
        taxon_id: int,
        species_confidence: float,
        detection_count: int,
    ) -> int:
        """Create a new visit.

        Args:
            file_id: File ID
            taxon_id: iNaturalist taxon ID
            species_confidence: Average species confidence
            detection_count: Number of detections

        Returns:
            Visit ID
        """
        with db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO visits
                (file_id, inaturalist_taxon_id, species_confidence,
                 species_confidence_model, detection_count)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    file_id,
                    taxon_id,
                    species_confidence,
                    BIOCLIP_MODEL_NAME,
                    detection_count,
                ),
            )
            return cursor.lastrowid

    def update(
        self,
        visit_id: int,
        species_confidence: float,
        detection_count: int,
    ):
        """Update an existing visit.

        Args:
            visit_id: Visit ID
            species_confidence: Average species confidence
            detection_count: Number of detections
        """
        with db.get_connection() as conn:
            conn.execute(
                """
                UPDATE visits
                SET species_confidence = ?,
                    species_confidence_model = ?,
                    detection_count = ?
                WHERE id = ?
            """,
                (
                    species_confidence,
                    BIOCLIP_MODEL_NAME,
                    detection_count,
                    visit_id,
                ),
            )

    def delete_detections(self, visit_id: int):
        """Delete all detections for a visit.

        Args:
            visit_id: Visit ID
        """
        with db.get_connection() as conn:
            conn.execute("DELETE FROM detections WHERE visit_id = ?", (visit_id,))

    def add_detection(self, visit_id: int, detection: Dict) -> int:
        """Add a detection to a visit.

        Args:
            visit_id: Visit ID
            detection: Detection dictionary

        Returns:
            Detection ID
        """
        with db.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO detections
                (visit_id, frame_number, frame_timestamp,
                 detection_confidence, detection_confidence_model,
                 species_confidence, species_confidence_model,
                 bbox_x1, bbox_y1, bbox_x2, bbox_y2,
                 crop_path, is_edge_detection)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    visit_id,
                    detection["frame_number"],
                    detection["frame_timestamp"],
                    detection["detection_confidence"],
                    YOLO_MODEL_PATH.replace(".pt", ""),
                    detection.get("species_confidence"),
                    BIOCLIP_MODEL_NAME,
                    detection["bbox"][0],
                    detection["bbox"][1],
                    detection["bbox"][2],
                    detection["bbox"][3],
                    detection.get("crop_path"),
                    1 if detection.get("is_edge", False) else 0,
                ),
            )
            return cursor.lastrowid

    def update_cover_detection(
        self, visit_id: int, best_detection_id: int, cover_detection_id: int
    ):
        """Update visit with cover detection IDs.

        Args:
            visit_id: Visit ID
            best_detection_id: ID of best detection
            cover_detection_id: ID of cover detection
        """
        with db.get_connection() as conn:
            conn.execute(
                """
                UPDATE visits
                SET best_detection_id = ?, cover_detection_id = ?
                WHERE id = ?
            """,
                (best_detection_id, cover_detection_id, visit_id),
            )
