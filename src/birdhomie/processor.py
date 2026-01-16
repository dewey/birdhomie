"""File processor for bird detection and classification."""

import logging
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict
import cv2
from PIL import Image
from .config import Config
from .constants import OUTPUT_DIR
from .detector import BirdDetector
from .classifier import BirdSpeciesClassifier
from .inaturalist import get_or_create_taxon
from .wikipedia import fetch_and_store_wikipedia_pages
from .video_processor import VideoFrameExtractor, VideoAnnotator
from .visit_grouper import VisitGrouper
from .repositories import FileRepository, VisitRepository
from .utils import track_timing
from .model_cache import get_detector, get_classifier

logger = logging.getLogger(__name__)


class FileProcessor:
    """Processes video files for bird detection and classification."""

    def __init__(
        self,
        config: Config,
        detector: BirdDetector = None,
        classifier: BirdSpeciesClassifier = None,
        file_repo: FileRepository = None,
        visit_repo: VisitRepository = None,
        frame_extractor: VideoFrameExtractor = None,
        annotator: VideoAnnotator = None,
        visit_grouper: VisitGrouper = None,
    ):
        """Initialize the file processor.

        Args:
            config: Application configuration
            detector: Bird detector (optional, will use cached instance if None)
            classifier: Species classifier (optional, will use cached instance if None)
            file_repo: File repository (optional, will create if None)
            visit_repo: Visit repository (optional, will create if None)
            frame_extractor: Frame extractor (optional, will create if None)
            annotator: Video annotator (optional, will create if None)
            visit_grouper: Visit grouper (optional, will create if None)
        """
        self.config = config
        # Use cached models if not explicitly provided
        self.detector = detector or get_detector(config)
        self.classifier = classifier or get_classifier()
        self.file_repo = file_repo or FileRepository()
        self.visit_repo = visit_repo or VisitRepository()
        self.frame_extractor = frame_extractor or VideoFrameExtractor(
            frame_skip=config.frame_skip
        )
        self.annotator = annotator or VideoAnnotator()
        self.visit_grouper = visit_grouper or VisitGrouper(
            min_species_confidence=config.min_species_confidence
        )

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
        existing = self.file_repo.get_by_hash(file_hash)

        if existing and existing["status"] == "success":
            logger.info("file_already_processed", extra={"file": str(file_path)})
            return False

        # Update or insert file record
        if existing:
            file_id = existing["id"]
            self.file_repo.mark_processing(file_id)
        else:
            # Get file metadata from filename or stat
            event_start = file_path.stat().st_mtime
            from datetime import datetime

            event_start_dt = datetime.fromtimestamp(event_start)
            file_id = self.file_repo.create(file_path, file_hash, event_start_dt)

        # Create output directory
        output_dir = OUTPUT_DIR / str(file_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        crops_dir = output_dir / "crops"
        crops_dir.mkdir(exist_ok=True)

        try:
            # Process the video
            duration = self._process_video(file_path, file_id, output_dir, crops_dir)

            # Update file record with success
            self.file_repo.mark_success(file_id, duration, f"output/{file_id}")

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

            self.file_repo.mark_failed(file_id, str(e))
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

        # Get video info
        video_info = self.frame_extractor.get_video_info(file_path)
        fps = video_info["fps"]
        height = video_info["height"]
        width = video_info["width"]
        total_frames = video_info["total_frames"]

        # Process frames
        all_detections = []
        detections_by_frame = {}  # For annotation
        log_interval = max(100, total_frames // 10)

        for frame_idx, frame in self.frame_extractor.extract_frames(file_path):
            # Log progress periodically
            if frame_idx > 0 and frame_idx % log_interval == 0:
                progress_pct = (
                    (frame_idx / total_frames) * 100 if total_frames > 0 else 0
                )
                logger.info(
                    "video_processing_progress",
                    extra={
                        "file_id": file_id,
                        "frame": frame_idx,
                        "total_frames": total_frames,
                        "progress_pct": f"{progress_pct:.1f}%",
                        "detections_so_far": len(all_detections),
                    },
                )

            # Detect birds
            detections = self.detector.detect_birds(frame)
            detections_by_frame[frame_idx] = detections

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
                    pil_crop = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
                    species_name, species_confidence = (
                        self.classifier.classify_from_array(pil_crop)
                    )
                    logger.debug(
                        "species_classified",
                        extra={
                            "frame": frame_idx,
                            "species": species_name,
                            "confidence": species_confidence,
                            "passes_threshold": species_confidence
                            and species_confidence
                            >= self.config.min_species_confidence,
                        },
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

        # Create annotated video
        annotated_path = output_dir / "annotated.mp4"
        self.annotator.create_annotated_video(
            file_path, annotated_path, self.config.frame_skip, detections_by_frame
        )

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

    def _create_visits_from_detections(self, file_id: int, detections: List[Dict]):
        """Group detections into visits by species.

        Args:
            file_id: Database file ID
            detections: List of detection dictionaries
        """
        # Group detections by species
        species_groups = self.visit_grouper.group_detections(detections)

        if not species_groups:
            logger.warning(
                "no_high_confidence_detections",
                extra={"file_id": file_id, "total_detections": len(detections)},
            )
            return

        logger.info(
            f"species_groups_created: {list(species_groups.keys())}",
            extra={
                "file_id": file_id,
                "species_count": len(species_groups),
                "species": list(species_groups.keys()),
            },
        )

        # Create visits for each species
        for species_name, species_detections in species_groups.items():
            # Get or create taxon
            taxon_id = get_or_create_taxon(species_name)

            if not taxon_id:
                logger.warning("taxon_creation_failed", extra={"species": species_name})
                continue

            # Get visit summary
            summary = self.visit_grouper.get_visit_summary(species_detections)

            # Check if visit already exists
            existing_visit = self.visit_repo.get_by_file_and_taxon(file_id, taxon_id)

            if existing_visit:
                # Update existing visit
                visit_id = existing_visit["id"]
                self.visit_repo.update(
                    visit_id,
                    summary["avg_species_confidence"],
                    summary["detection_count"],
                )
                # Delete old detections
                self.visit_repo.delete_detections(visit_id)
            else:
                # Create new visit
                visit_id = self.visit_repo.create(
                    file_id,
                    taxon_id,
                    summary["avg_species_confidence"],
                    summary["detection_count"],
                )

            # Insert all detections for this visit
            best_detection_id = None
            for idx, det in enumerate(species_detections):
                detection_id = self.visit_repo.add_detection(visit_id, det)
                # Track the best detection
                if idx == summary["best_detection_idx"]:
                    best_detection_id = detection_id

            # Update visit with cover detection
            if best_detection_id:
                self.visit_repo.update_cover_detection(
                    visit_id, best_detection_id, best_detection_id
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
        pending_files = self.file_repo.get_pending_files()

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
