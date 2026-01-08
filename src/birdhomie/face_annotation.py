"""Face bbox annotation using heuristic approach."""

from typing import Tuple
import logging

logger = logging.getLogger(__name__)


def calculate_face_bbox(
    bbox_x1: int, bbox_y1: int, bbox_x2: int, bbox_y2: int
) -> Tuple[int, int, int, int]:
    """
    Calculate face bounding box using heuristic approach.

    Strategy: Face is typically in upper 25% of bird detection bbox.
    Creates a bbox covering the top portion where head/face should be.
    Adds 5% inset on sides to ensure drag handles are always visible.

    Args:
        bbox_x1: Left edge of bird detection bbox
        bbox_y1: Top edge of bird detection bbox
        bbox_x2: Right edge of bird detection bbox
        bbox_y2: Bottom edge of bird detection bbox

    Returns:
        Tuple of (face_x1, face_y1, face_x2, face_y2)
    """
    width = bbox_x2 - bbox_x1
    height = bbox_y2 - bbox_y1

    # Add 5% inset to keep handles visible and easier to grab
    horizontal_inset = int(width * 0.05)
    vertical_inset = int(height * 0.02)  # Smaller vertical inset

    # Face bbox: 90% width (5% inset on each side), upper 25% of height
    face_x1 = bbox_x1 + horizontal_inset
    face_y1 = bbox_y1 + vertical_inset
    face_x2 = bbox_x2 - horizontal_inset
    face_y2 = bbox_y1 + int(height * 0.25) + vertical_inset

    logger.debug(
        f"Calculated face bbox [{face_x1}, {face_y1}, {face_x2}, {face_y2}] "
        f"from detection bbox [{bbox_x1}, {bbox_y1}, {bbox_x2}, {bbox_y2}]"
    )

    return face_x1, face_y1, face_x2, face_y2


def annotate_detection(conn, detection_id: int) -> bool:
    """
    Annotate a single detection with face bbox using heuristic.

    Args:
        conn: Database connection
        detection_id: ID of detection to annotate

    Returns:
        True if annotated successfully, False if skipped/failed
    """
    detection = conn.execute("""
        SELECT id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, annotation_source
        FROM detections
        WHERE id = ?
    """, (detection_id,)).fetchone()

    if not detection:
        logger.warning(f"Detection {detection_id} not found")
        return False

    if detection['annotation_source'] is not None:
        logger.debug(f"Detection {detection_id} already annotated")
        return False

    # Calculate face bbox
    face_x1, face_y1, face_x2, face_y2 = calculate_face_bbox(
        detection['bbox_x1'],
        detection['bbox_y1'],
        detection['bbox_x2'],
        detection['bbox_y2']
    )

    # Update detection with annotation
    conn.execute("""
        UPDATE detections
        SET face_bbox_x1 = ?,
            face_bbox_y1 = ?,
            face_bbox_x2 = ?,
            face_bbox_y2 = ?,
            annotation_source = 'machine',
            annotated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (face_x1, face_y1, face_x2, face_y2, detection_id))

    logger.info(f"Annotated detection {detection_id}")
    return True


def annotate_batch(batch_size: int) -> int:
    """
    Annotate a batch of unannotated detections.

    Called by periodic background task.

    Args:
        batch_size: Maximum number of detections to annotate in one run

    Returns:
        Number of detections annotated
    """
    from . import database as db

    with db.get_connection() as conn:
        # Find unannotated detections
        unannotated = conn.execute("""
            SELECT id
            FROM detections
            WHERE annotation_source IS NULL
            ORDER BY id ASC
            LIMIT ?
        """, (batch_size,)).fetchall()

        if not unannotated:
            logger.debug("No unannotated detections found")
            return 0

        logger.info(f"Found {len(unannotated)} unannotated detections")

        annotated_count = 0
        for row in unannotated:
            if annotate_detection(conn, row['id']):
                annotated_count += 1

        conn.commit()

        logger.info(f"Annotated {annotated_count}/{len(unannotated)} detections")
        return annotated_count
