"""Background task scheduler."""

import logging
import signal
import sys
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from .config import Config
from .utils import task_lock
from .processor import process_files_sync
from .unifi import download_unifi_events_sync
from . import database as db

logger = logging.getLogger(__name__)


def shutdown_scheduler(scheduler, signum, frame):
    """Gracefully shutdown scheduler on SIGTERM/SIGINT."""
    logger.info("shutdown_signal_received", extra={"signal": signum})
    if scheduler.running:
        scheduler.shutdown(wait=True)
    sys.exit(0)


def process_files_task(config: Config):
    """File processor task with locking to prevent overlaps."""
    try:
        with task_lock("file_processor") as task_id:
            items_processed = process_files_sync(config)

            # Update items_processed count
            with db.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE task_runs
                    SET items_processed = ?
                    WHERE id = ?
                """,
                    (items_processed, task_id),
                )

            logger.info(
                "file_processor_completed",
                extra={"task_id": task_id, "items_processed": items_processed},
            )
    except BlockingIOError:
        logger.warning("file_processor_already_running")


def download_unifi_task(config: Config):
    """UniFi download task with locking."""
    try:
        with task_lock("unifi_download") as task_id:
            items_downloaded = download_unifi_events_sync(config, hours=72)

            # Update items_processed count
            with db.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE task_runs
                    SET items_processed = ?
                    WHERE id = ?
                """,
                    (items_downloaded, task_id),
                )

            logger.info(
                "unifi_download_completed",
                extra={"task_id": task_id, "items_downloaded": items_downloaded},
            )

            # Trigger processing automatically if new items were downloaded
            if items_downloaded > 0:
                logger.info(
                    "triggering_file_processor_after_download",
                    extra={"items_downloaded": items_downloaded},
                )
                process_files_task(config)
    except BlockingIOError:
        logger.warning("unifi_download_already_running")


def face_annotation_task(config: Config):
    """Face annotation task with locking to prevent overlaps."""
    from .face_annotation import annotate_batch

    try:
        with task_lock("face_annotation") as task_id:
            items_annotated = annotate_batch(
                batch_size=config.face_annotation_batch_size
            )

            # Update items_processed count
            with db.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE task_runs
                    SET items_processed = ?
                    WHERE id = ?
                """,
                    (items_annotated, task_id),
                )

            logger.info(
                "face_annotation_completed",
                extra={"task_id": task_id, "items_annotated": items_annotated},
            )
    except BlockingIOError:
        logger.warning("face_annotation_already_running")


def regenerate_thumbnails_task(config: Config):
    """Update timestamps for all detections to force thumbnail regeneration."""
    try:
        with task_lock("regenerate_thumbnails") as task_id:
            with db.get_connection() as conn:
                result = conn.execute("""
                    UPDATE detections
                    SET reviewed_at = CURRENT_TIMESTAMP
                    WHERE crop_path IS NOT NULL
                """)
                items_regenerated = result.rowcount
                conn.commit()

                conn.execute(
                    """
                    UPDATE task_runs
                    SET items_processed = ?
                    WHERE id = ?
                """,
                    (items_regenerated, task_id),
                )
                conn.commit()

            logger.info(
                "thumbnail_regeneration_completed",
                extra={"task_id": task_id, "items_regenerated": items_regenerated},
            )
    except BlockingIOError:
        logger.warning("thumbnail_regeneration_already_running")


def cleanup_stale_tasks():
    """Mark any running tasks as failed on startup.

    This handles cases where the application was restarted while tasks were running.
    """
    import socket
    import os

    current_hostname = socket.gethostname()
    current_pid = os.getpid()

    with db.get_connection() as conn:
        # Find all tasks that are marked as running
        stale_tasks = conn.execute("""
            SELECT id, task_type, hostname, pid
            FROM task_runs
            WHERE status = 'running'
        """).fetchall()

        for task in stale_tasks:
            # Check if it's from a different process or hostname
            if task["hostname"] != current_hostname or task["pid"] != current_pid:
                conn.execute(
                    """
                    UPDATE task_runs
                    SET status = 'failed',
                        completed_at = CURRENT_TIMESTAMP,
                        error_message = 'Task interrupted by application restart'
                    WHERE id = ?
                """,
                    (task["id"],),
                )

                logger.warning(
                    "cleaned_up_stale_task",
                    extra={
                        "task_id": task["id"],
                        "task_type": task["task_type"],
                        "old_hostname": task["hostname"],
                        "old_pid": task["pid"],
                    },
                )

        conn.commit()

        if stale_tasks:
            logger.info("stale_tasks_cleaned_up", extra={"count": len(stale_tasks)})


def start_scheduler(config: Config) -> BackgroundScheduler:
    """Start the background task scheduler.

    Args:
        config: Application configuration

    Returns:
        Running scheduler instance
    """
    # Clean up any stale tasks from previous runs
    cleanup_stale_tasks()

    executors = {"default": ThreadPoolExecutor(max_workers=2)}

    scheduler = BackgroundScheduler(executors=executors)

    # Register shutdown handler
    signal.signal(signal.SIGTERM, lambda s, f: shutdown_scheduler(scheduler, s, f))
    signal.signal(signal.SIGINT, lambda s, f: shutdown_scheduler(scheduler, s, f))

    # Configure periodic tasks
    scheduler.add_job(
        process_files_task,
        "interval",
        minutes=config.processor_interval_minutes,
        id="file_processor",
        args=[config],
    )

    scheduler.add_job(
        download_unifi_task,
        "interval",
        minutes=config.ufp_download_interval_minutes,
        id="unifi_download",
        args=[config],
    )

    # Face annotation task
    scheduler.add_job(
        face_annotation_task,
        "interval",
        minutes=10,
        id="face_annotation",
        name="Annotate bird faces",
        args=[config],
    )

    scheduler.start()
    logger.info(
        "scheduler_started",
        extra={
            "processor_interval": config.processor_interval_minutes,
            "download_interval": config.ufp_download_interval_minutes,
            "face_annotation_interval": 10,
        },
    )

    return scheduler
