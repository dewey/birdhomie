"""Prometheus metrics for birdhomie."""

from dataclasses import dataclass
from datetime import datetime
from prometheus_client import Counter, Histogram, Gauge, Info

from . import database as db

# Job execution metrics
JOB_DURATION = Histogram(
    "birdhomie_job_duration_seconds",
    "Duration of background jobs in seconds",
    ["job_type", "status"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
)

JOB_RUNS_TOTAL = Counter(
    "birdhomie_job_runs_total",
    "Total number of job runs",
    ["job_type", "status"],
)

ITEMS_PROCESSED_TOTAL = Counter(
    "birdhomie_items_processed_total",
    "Total items processed by jobs",
    ["job_type"],
)

# Application state gauges (updated from database)
DETECTIONS_TOTAL = Gauge(
    "birdhomie_detections_total",
    "Total number of bird detections in database",
)

VISITS_TOTAL = Gauge(
    "birdhomie_visits_total",
    "Total number of bird visits in database",
)

FILES_PROCESSED = Gauge(
    "birdhomie_files_processed_total",
    "Total files processed (success + failed)",
)

FILES_PENDING = Gauge(
    "birdhomie_files_pending",
    "Files waiting to be processed",
)

# Application info
APP_INFO = Info(
    "birdhomie",
    "Application information",
)
APP_INFO.info({"version": "0.1.0"})


def update_gauges():
    """Update gauge metrics from database.

    Called before generating metrics output to ensure fresh values.
    """
    with db.get_connection() as conn:
        stats = conn.execute("""
            SELECT
                (SELECT COUNT(*) FROM detections) as detections,
                (SELECT COUNT(*) FROM visits WHERE deleted_at IS NULL) as visits,
                (SELECT COUNT(*) FROM files WHERE status IN ('success', 'failed')) as processed,
                (SELECT COUNT(*) FROM files WHERE status = 'pending') as pending
        """).fetchone()

        DETECTIONS_TOTAL.set(stats["detections"])
        VISITS_TOTAL.set(stats["visits"])
        FILES_PROCESSED.set(stats["processed"])
        FILES_PENDING.set(stats["pending"])


# Legacy dataclass for web UI compatibility
@dataclass
class Metrics:
    """Application metrics for web UI display."""

    files_processed_total: int = 0
    detections_total: int = 0
    visits_total: int = 0
    processing_errors_total: int = 0
    avg_processing_time_seconds: float = 0.0
    last_updated: datetime = None


def get_metrics() -> Metrics:
    """Get current application metrics from database.

    Used by web UI to display stats. Also updates Prometheus gauges.
    """
    with db.get_connection() as conn:
        stats = conn.execute("""
            SELECT
                COUNT(*) as files_processed,
                (SELECT COUNT(*) FROM detections) as detections,
                (SELECT COUNT(*) FROM visits WHERE deleted_at IS NULL) as visits,
                (SELECT COUNT(*) FROM files WHERE status = 'failed') as errors,
                (SELECT AVG(duration_seconds) FROM task_runs
                 WHERE task_type = 'file_processor' AND status = 'success') as avg_time
            FROM files
            WHERE status IN ('success', 'failed')
        """).fetchone()

        # Update Prometheus gauges while we have fresh data
        DETECTIONS_TOTAL.set(stats["detections"])
        VISITS_TOTAL.set(stats["visits"])
        FILES_PROCESSED.set(stats["files_processed"])

        return Metrics(
            files_processed_total=stats["files_processed"],
            detections_total=stats["detections"],
            visits_total=stats["visits"],
            processing_errors_total=stats["errors"],
            avg_processing_time_seconds=stats["avg_time"] or 0.0,
            last_updated=datetime.now(),
        )
