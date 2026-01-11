"""File processor for bird detection and classification."""

import logging
import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict
import cv2
from PIL import Image
from .config import Config
from .constants import OUTPUT_DIR, YOLO_MODEL_PATH, BIOCLIP_MODEL_NAME
from .detector import BirdDetector
from .classifier import BirdSpeciesClassifier
from .inaturalist import get_or_create_taxon
from .wikipedia import fetch_and_store_wikipedia_pages
from . import database as db
from .utils import track_timing

logger = logging.getLogger(__name__)


class FileProcessor:
    """Processes video files for bird detection and classification."""

    def __init__(self, config: Config):
        """Initialize the file processor.

        Args:
            config: Application configuration
        """
        self.config = config
        self.detector = BirdDetector(
            model_path=YOLO_MODEL_PATH,
            confidence_threshold=config.min_detection_confidence,
        )
        self.classifier = BirdSpeciesClassifier()

        logger.info(
            "file_processor_initialized",
            extra={
                "detection_threshold": config.min_detection_confidence,
                "species_threshold": config.min_species_confidence,
            },
        )

    @track_timing("file_processing")
    def process_file(self, file_path: Path) -> bool:
        """Process a single video file.

        Args:
            file_path: Path to the video file

        Returns:
            True if successful, False otherwise
        """
        logger.info("processing_file", extra={"file": str(file_path)})

        # Get or create file record
        file_hash = self._calculate_file_hash(file_path)

        with db.get_connection() as conn:
            # Check if already processed
            existing = conn.execute(
                """
                SELECT id, status FROM files
                WHERE file_hash = ?
            """,
                (file_hash,),
            ).fetchone()

            if existing and existing["status"] == "success":
                logger.info("file_already_processed", extra={"file": str(file_path)})
                return False

            # Update or insert file record
            if existing:
                file_id = existing["id"]
                conn.execute(
                    """
                    UPDATE files
                    SET status = 'processing', processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (file_id,),
                )
            else:
                # Get file metadata from filename or stat
                event_start = file_path.stat().st_mtime
                from datetime import datetime

                event_start_dt = datetime.fromtimestamp(event_start)

                cursor = conn.execute(
                    """
                    INSERT INTO files
                    (file_path, file_hash, event_start, status)
                    VALUES (?, ?, ?, 'processing')
                """,
                    (str(file_path), file_hash, event_start_dt),
                )
                file_id = cursor.lastrowid

        # Create output directory
        output_dir = OUTPUT_DIR / str(file_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        crops_dir = output_dir / "crops"
        crops_dir.mkdir(exist_ok=True)

        try:
            # Process the video
            duration = self._process_video(file_path, file_id, output_dir, crops_dir)

            # Update file record with success
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
                    (duration, str(output_dir), file_id),
                )

            logger.info(
                "file_processed_successfully",
                extra={
                    "file": str(file_path),
                    "file_id": file_id,
                    "duration": duration,
                },
            )

            return True

        except Exception as e:
            logger.error(
                "file_processing_failed",
                extra={"file": str(file_path), "file_id": file_id, "error": str(e)},
            )

            with db.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE files
                    SET status = 'failed',
                        error_message = ?,
                        processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (str(e), file_id),
                )

            return False

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _process_video(
        self, file_path: Path, file_id: int, output_dir: Path, crops_dir: Path
    ) -> float:
        """Process a video file and extract detections.

        Args:
            file_path: Path to video file
            file_id: Database file ID
            output_dir: Output directory for results
            crops_dir: Directory for cropped images

        Returns:
            Video duration in seconds
        """
        logger.info(
            "video_processing_started",
            extra={"file": str(file_path), "file_id": file_id},
        )

        # Open video with OpenCV for processing
        cap = cv2.VideoCapture(str(file_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Prepare annotated video writer
        annotated_path = output_dir / "annotated.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(annotated_path), fourcc, fps, (width, height))

        # Process frames
        frame_idx = 0
        all_detections = []  # Store all detections for grouping

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Process every Nth frame
            if frame_idx % self.config.frame_skip == 0:
                detections = self.detector.detect_birds(frame)

                # Draw detections on frame
                annotated_frame = frame.copy()
                for det in detections:
                    x1, y1, x2, y2 = det["bbox"]
                    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    conf_text = f"{det['confidence']:.2f}"
                    cv2.putText(
                        annotated_frame,
                        conf_text,
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        2,
                    )

                # Process each detection
                for det_idx, det in enumerate(detections):
                    x1, y1, x2, y2 = det["bbox"]
                    confidence = det["confidence"]

                    # Save crop
                    crop = frame[y1:y2, x1:x2]
                    crop_filename = f"frame_{frame_idx:06d}_det{det_idx:02d}.jpg"
                    crop_path = crops_dir / crop_filename
                    cv2.imwrite(str(crop_path), crop)

                    # Check if edge detection
                    is_edge = self.detector.is_edge_detection(
                        (x1, y1, x2, y2), (height, width)
                    )

                    # Classify species (skip edge detections)
                    species_name = None
                    species_confidence = None

                    if not is_edge:
                        pil_crop = Image.fromarray(
                            cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                        )
                        species_name, species_confidence = (
                            self.classifier.classify_from_array(pil_crop)
                        )

                    # Store detection info
                    all_detections.append(
                        {
                            "frame_number": frame_idx,
                            "frame_timestamp": frame_idx / fps,
                            "detection_confidence": confidence,
                            "species_name": species_name,
                            "species_confidence": species_confidence,
                            "bbox": (x1, y1, x2, y2),
                            "crop_path": str(crop_path.relative_to(output_dir.parent)),
                            "is_edge": is_edge,
                        }
                    )

                out.write(annotated_frame)
            else:
                out.write(frame)

            frame_idx += 1

        cap.release()
        out.release()

        # Convert to H.264
        self._convert_to_h264(annotated_path)

        # Group detections into visits
        self._create_visits_from_detections(file_id, all_detections)

        duration = total_frames / fps if fps > 0 else 0.0

        logger.info(
            "video_processing_complete",
            extra={
                "file_id": file_id,
                "total_detections": len(all_detections),
                "duration": duration,
            },
        )

        return duration

    def _convert_to_h264(self, video_path: Path):
        """Convert video to H.264 codec for browser compatibility."""
        temp_path = video_path.with_suffix(".temp.mp4")
        video_path.rename(temp_path)

        try:
            # Try hardware acceleration first (macOS)
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(temp_path),
                    "-c:v",
                    "h264_videotoolbox",
                    "-b:v",
                    "5M",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    str(video_path),
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )
            temp_path.unlink()
            logger.info("video_converted_h264", extra={"path": str(video_path)})
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            # Fallback to software encoding
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(temp_path),
                        "-c:v",
                        "libx264",
                        "-preset",
                        "fast",
                        "-crf",
                        "23",
                        "-c:a",
                        "aac",
                        "-movflags",
                        "+faststart",
                        str(video_path),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=300,
                )
                temp_path.unlink()
                logger.info(
                    "video_converted_h264_software", extra={"path": str(video_path)}
                )
            except Exception as e:
                temp_path.rename(video_path)
                logger.warning("video_conversion_failed", extra={"error": str(e)})

    def _create_visits_from_detections(self, file_id: int, detections: List[Dict]):
        """Group detections into visits by species.

        Args:
            file_id: Database file ID
            detections: List of detection dictionaries
        """
        # Filter high-confidence detections
        high_conf = [
            d
            for d in detections
            if d["species_confidence"]
            and d["species_confidence"] >= self.config.min_species_confidence
        ]

        if not high_conf:
            logger.info("no_high_confidence_detections", extra={"file_id": file_id})
            return

        # Group by species
        species_groups: Dict[str, List[Dict]] = {}
        for det in high_conf:
            species = det["species_name"]
            if species not in species_groups:
                species_groups[species] = []
            species_groups[species].append(det)

        logger.info(
            "species_groups_created",
            extra={"file_id": file_id, "species_count": len(species_groups)},
        )

        # Create visits
        for species_name, species_detections in species_groups.items():
            # Get or create taxon
            taxon_id = get_or_create_taxon(species_name)

            if not taxon_id:
                logger.warning("taxon_creation_failed", extra={"species": species_name})
                continue

            # Find best detection
            best_det = max(species_detections, key=lambda d: d["detection_confidence"])
            avg_species_conf = sum(
                d["species_confidence"] for d in species_detections
            ) / len(species_detections)

            with db.get_connection() as conn:
                # Check if visit already exists for this file and species
                existing_visit = conn.execute(
                    """
                    SELECT id FROM visits
                    WHERE file_id = ? AND inaturalist_taxon_id = ?
                """,
                    (file_id, taxon_id),
                ).fetchone()

                if existing_visit:
                    # Update existing visit
                    visit_id = existing_visit["id"]
                    conn.execute(
                        """
                        UPDATE visits
                        SET species_confidence = ?,
                            species_confidence_model = ?,
                            detection_count = ?
                        WHERE id = ?
                    """,
                        (
                            avg_species_conf,
                            BIOCLIP_MODEL_NAME,
                            len(species_detections),
                            visit_id,
                        ),
                    )

                    # Delete old detections for this visit
                    conn.execute(
                        "DELETE FROM detections WHERE visit_id = ?", (visit_id,)
                    )
                else:
                    # Create new visit
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
                            avg_species_conf,
                            BIOCLIP_MODEL_NAME,
                            len(species_detections),
                        ),
                    )
                    visit_id = cursor.lastrowid

                # Insert all detections for this visit
                for det in species_detections:
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
                            det["frame_number"],
                            det["frame_timestamp"],
                            det["detection_confidence"],
                            YOLO_MODEL_PATH.replace(".pt", ""),
                            det["species_confidence"],
                            BIOCLIP_MODEL_NAME,
                            det["bbox"][0],
                            det["bbox"][1],
                            det["bbox"][2],
                            det["bbox"][3],
                            det["crop_path"],
                            1 if det["is_edge"] else 0,
                        ),
                    )

                    # Set cover detection (auto-populate with best)
                    if det is best_det:
                        best_detection_id = cursor.lastrowid

                # Update visit with cover detection (auto-set to best)
                conn.execute(
                    """
                    UPDATE visits
                    SET best_detection_id = ?, cover_detection_id = ?
                    WHERE id = ?
                """,
                    (best_detection_id, best_detection_id, visit_id),
                )

            logger.info(
                "visit_created",
                extra={
                    "visit_id": visit_id,
                    "species": species_name,
                    "taxon_id": taxon_id,
                    "detection_count": len(species_detections),
                },
            )

            # Fetch Wikipedia pages asynchronously (in background)
            try:
                fetch_and_store_wikipedia_pages(taxon_id)
            except Exception as e:
                logger.error(
                    "wikipedia_fetch_failed",
                    extra={"taxon_id": taxon_id, "error": str(e)},
                )

    def process_pending_files(self) -> int:
        """Process all pending files in the database.

        Returns:
            Number of files processed
        """
        with db.get_connection() as conn:
            pending_files = conn.execute("""
                SELECT file_path FROM files
                WHERE status = 'pending'
                ORDER BY created_at
            """).fetchall()

        # Filter to existing files
        file_paths = []
        for row in pending_files:
            file_path = Path(row["file_path"])
            if file_path.exists():
                file_paths.append(file_path)
            else:
                logger.warning("file_not_found", extra={"file": str(file_path)})

        if not file_paths:
            return 0

        workers = self.config.processor_workers
        if workers > 1:
            logger.info(
                "processing_files_parallel",
                extra={"count": len(file_paths), "workers": workers},
            )
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(self.process_file, file_paths))
            return sum(results)
        else:
            count = 0
            for file_path in file_paths:
                if self.process_file(file_path):
                    count += 1
            return count


def process_files_sync(config: Config) -> int:
    """Process all pending files synchronously.

    Args:
        config: Application configuration

    Returns:
        Number of files processed
    """
    processor = FileProcessor(config)
    return processor.process_pending_files()
