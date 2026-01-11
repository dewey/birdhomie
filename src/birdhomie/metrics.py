"""Performance metrics tracking."""

from dataclasses import dataclass
from datetime import datetime
from . import database as db


@dataclass
class Metrics:
    """Application metrics."""

    files_processed_total: int = 0
    detections_total: int = 0
    visits_total: int = 0
    processing_errors_total: int = 0
    avg_processing_time_seconds: float = 0.0
    last_updated: datetime = None


def get_metrics() -> Metrics:
    """Get current application metrics from database."""
    with db.get_connection() as conn:
        stats = conn.execute("""
            SELECT
                COUNT(*) as files_processed,
                (SELECT COUNT(*) FROM detections) as detections,
                (SELECT COUNT(*) FROM visits) as visits,
                (SELECT COUNT(*) FROM files WHERE status = 'failed') as errors,
                (SELECT AVG(duration_seconds) FROM task_runs
                 WHERE task_type = 'file_processor' AND status = 'success') as avg_time
            FROM files
            WHERE status IN ('success', 'failed')
        """).fetchone()

        return Metrics(
            files_processed_total=stats["files_processed"],
            detections_total=stats["detections"],
            visits_total=stats["visits"],
            processing_errors_total=stats["errors"],
            avg_processing_time_seconds=stats["avg_time"] or 0.0,
            last_updated=datetime.now(),
        )
