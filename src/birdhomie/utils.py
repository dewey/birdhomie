"""Utility functions for retry logic, circuit breaker, and task locking."""

import time
import logging
import socket
import os
from functools import wraps
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def retry_on_failure(max_attempts=3, delay=1.0, backoff=2.0):
    """Retry decorator with exponential backoff for external API calls."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 1
            current_delay = delay

            while attempt <= max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts:
                        logger.error(
                            "retry_exhausted",
                            extra={
                                "function": func.__name__,
                                "attempts": attempt,
                                "error": str(e),
                            },
                        )
                        raise

                    logger.warning(
                        "retry_attempt",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt,
                            "delay": current_delay,
                            "error": str(e),
                        },
                    )

                    time.sleep(current_delay)
                    current_delay *= backoff
                    attempt += 1

        return wrapper

    return decorator


class CircuitBreaker:
    """Prevent cascading failures from external services."""

    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = "closed"

    def call(self, func, *args, **kwargs):
        if self.state == "open":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "half_open"
                logger.info("circuit_breaker_half_open")
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            if self.state == "half_open":
                self.state = "closed"
                self.failure_count = 0
                logger.info("circuit_breaker_closed")
            return result
        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.error(
                    "circuit_breaker_opened",
                    extra={"failure_count": self.failure_count},
                )
            raise


@contextmanager
def task_lock(task_type: str):
    """Prevent concurrent execution of same task using database status check."""
    from . import database as db
    from . import metrics as m

    with db.get_connection() as conn:
        # Check if task is already running
        existing = conn.execute(
            """
            SELECT id FROM task_runs
            WHERE task_type = ? AND status = 'running'
            ORDER BY started_at DESC LIMIT 1
        """,
            (task_type,),
        ).fetchone()

        if existing:
            logger.warning("task_already_running", extra={"task": task_type})
            raise BlockingIOError(f"Task {task_type} is already running")

        # Start new task run
        task_id = conn.execute(
            """
            INSERT INTO task_runs (task_type, hostname, pid, status)
            VALUES (?, ?, ?, 'running')
        """,
            (task_type, socket.gethostname(), os.getpid()),
        ).lastrowid
        conn.commit()

        logger.info("task_started", extra={"task": task_type, "task_id": task_id})

    start_time = time.time()
    try:
        yield task_id
    except Exception as e:
        # Record metrics for failed job
        duration = time.time() - start_time
        m.JOB_DURATION.labels(job_type=task_type, status="failed").observe(duration)
        m.JOB_RUNS_TOTAL.labels(job_type=task_type, status="failed").inc()

        # Mark as failed on exception
        with db.get_connection() as conn:
            conn.execute(
                """
                UPDATE task_runs
                SET status = 'failed',
                    completed_at = CURRENT_TIMESTAMP,
                    duration_seconds = (julianday(CURRENT_TIMESTAMP) - julianday(started_at)) * 86400.0,
                    error_message = ?
                WHERE id = ?
            """,
                (str(e), task_id),
            )
            conn.commit()
        raise
    else:
        # Record metrics for successful job
        duration = time.time() - start_time
        m.JOB_DURATION.labels(job_type=task_type, status="success").observe(duration)
        m.JOB_RUNS_TOTAL.labels(job_type=task_type, status="success").inc()

        # Mark as success
        with db.get_connection() as conn:
            conn.execute(
                """
                UPDATE task_runs
                SET status = 'success',
                    completed_at = CURRENT_TIMESTAMP,
                    duration_seconds = (julianday(CURRENT_TIMESTAMP) - julianday(started_at)) * 86400.0
                WHERE id = ?
            """,
                (task_id,),
            )
            conn.commit()


def track_timing(metric_name: str):
    """Decorator to track function execution time."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start
                logger.info(
                    "metric",
                    extra={
                        "metric": metric_name,
                        "duration_seconds": duration,
                        "status": "success",
                    },
                )
                return result
            except Exception as e:
                duration = time.time() - start
                logger.error(
                    "metric",
                    extra={
                        "metric": metric_name,
                        "duration_seconds": duration,
                        "status": "error",
                        "error": str(e),
                    },
                )
                raise

        return wrapper

    return decorator
