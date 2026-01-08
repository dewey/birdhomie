"""YOLO bird detection module."""

import logging
from pathlib import Path
from typing import List, Tuple
import numpy as np
from ultralytics import YOLO
from .constants import YOLO_MODEL_PATH, BIRD_CLASS_ID, MODELS_DIR

logger = logging.getLogger(__name__)


class BirdDetector:
    """YOLO-based bird detector."""

    def __init__(self, model_path: str = None, confidence_threshold: float = 0.80):
        """Initialize the bird detector.

        Args:
            model_path: Path to YOLO model file
            confidence_threshold: Minimum confidence for detections
        """
        self.model_path = model_path or YOLO_MODEL_PATH
        self.confidence_threshold = confidence_threshold
        self.model = None

        logger.info("loading_yolo_model", extra={
            "model_path": self.model_path,
            "confidence_threshold": confidence_threshold
        })

    def load_model(self):
        """Load the YOLO model. Downloads if not present."""
        if self.model is None:
            # Ensure models directory exists
            MODELS_DIR.mkdir(parents=True, exist_ok=True)

            # YOLO will auto-download yolov8m.pt if file doesn't exist
            self.model = YOLO(self.model_path)
            logger.info("yolo_model_loaded", extra={"model_path": self.model_path})

    def detect_birds(self, image: np.ndarray) -> List[dict]:
        """Detect birds in an image.

        Args:
            image: Input image as numpy array (BGR format)

        Returns:
            List of detections with bbox and confidence
        """
        if self.model is None:
            self.load_model()

        # Run inference
        results = self.model(image, verbose=False)

        detections = []
        for result in results:
            boxes = result.boxes
            for i in range(len(boxes)):
                # Check if it's a bird (class 14)
                class_id = int(boxes.cls[i])
                if class_id != BIRD_CLASS_ID:
                    continue

                confidence = float(boxes.conf[i])
                if confidence < self.confidence_threshold:
                    continue

                # Get bounding box coordinates
                x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()

                detections.append({
                    "bbox": (int(x1), int(y1), int(x2), int(y2)),
                    "confidence": confidence,
                    "class_id": class_id
                })

        return detections

    def is_edge_detection(self, bbox: Tuple[int, int, int, int], image_shape: Tuple[int, int], margin: int = 20) -> bool:
        """Check if bounding box touches image edges.

        Args:
            bbox: Bounding box (x1, y1, x2, y2)
            image_shape: Image dimensions (height, width)
            margin: Pixel margin from edge

        Returns:
            True if bbox is within margin pixels of any edge
        """
        x1, y1, x2, y2 = bbox
        height, width = image_shape[:2]

        return (
            x1 < margin or
            y1 < margin or
            x2 > width - margin or
            y2 > height - margin
        )
