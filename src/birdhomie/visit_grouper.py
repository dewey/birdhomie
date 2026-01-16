"""Groups detections into visits by species."""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class VisitGrouper:
    """Groups detections into visits by species."""

    def __init__(self, min_species_confidence: float = 0.85):
        """Initialize the visit grouper.

        Args:
            min_species_confidence: Minimum confidence threshold for species classification
        """
        self.min_species_confidence = min_species_confidence

    def group_detections(self, detections: List[Dict]) -> Dict[str, List[Dict]]:
        """Group detections by species.

        Args:
            detections: List of detection dictionaries with species info

        Returns:
            Dictionary mapping species_name to list of detections
        """
        # Filter high-confidence detections
        high_conf = [
            d
            for d in detections
            if d.get("species_confidence")
            and d["species_confidence"] >= self.min_species_confidence
        ]

        if not high_conf:
            # Log summary of filtered detections
            edge_count = sum(1 for d in detections if d.get("is_edge", False))
            null_conf_count = sum(
                1 for d in detections if d.get("species_confidence") is None
            )
            low_conf = [
                d
                for d in detections
                if d.get("species_confidence") is not None
                and d["species_confidence"] < self.min_species_confidence
            ]
            low_conf_species = {
                d.get("species_name"): d.get("species_confidence")
                for d in low_conf
                if d.get("species_name")
            }
            logger.warning(
                "no_high_confidence_detections",
                extra={
                    "total_detections": len(detections),
                    "edge_detections": edge_count,
                    "null_confidence": null_conf_count,
                    "low_confidence_species": low_conf_species,
                    "threshold": self.min_species_confidence,
                },
            )
            return {}

        # Group by species
        species_groups: Dict[str, List[Dict]] = {}
        for det in high_conf:
            species = det.get("species_name")
            if not species:
                continue
            if species not in species_groups:
                species_groups[species] = []
            species_groups[species].append(det)

        logger.info(
            f"species_groups_created: {list(species_groups.keys())}",
            extra={
                "species_count": len(species_groups),
                "species": list(species_groups.keys()),
            },
        )

        return species_groups

    def get_visit_summary(self, species_detections: List[Dict]) -> Dict:
        """Get summary statistics for a visit.

        Args:
            species_detections: List of detections for a single species

        Returns:
            Dictionary with best_detection_idx, avg_species_confidence, detection_count
        """
        if not species_detections:
            return {
                "best_detection_idx": None,
                "avg_species_confidence": 0.0,
                "detection_count": 0,
            }

        # Find best detection by detection confidence
        best_idx = 0
        best_conf = species_detections[0].get("detection_confidence", 0)
        for i, det in enumerate(species_detections):
            conf = det.get("detection_confidence", 0)
            if conf > best_conf:
                best_conf = conf
                best_idx = i

        # Calculate average species confidence
        avg_species_conf = sum(
            d.get("species_confidence", 0) for d in species_detections
        ) / len(species_detections)

        return {
            "best_detection_idx": best_idx,
            "avg_species_confidence": avg_species_conf,
            "detection_count": len(species_detections),
        }
