"""Gunicorn configuration for production deployment."""

import os
import logging

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
workers = int(os.getenv("GUNICORN_WORKERS", "2"))

# Worker settings
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "birdhomie"

# Preload app to share memory between workers (but scheduler starts after fork)
preload_app = False

# Store scheduler reference globally so we can shut it down
_scheduler = None


def on_starting(server):
    """Called just before the master process is initialized."""
    logger = logging.getLogger("gunicorn.error")
    logger.info("Gunicorn master process starting")


def when_ready(server):
    """Called just after the server is started.

    This runs in the master process, which is ideal for the scheduler
    since it won't be duplicated across workers.
    """
    global _scheduler
    logger = logging.getLogger("gunicorn.error")

    # Import here to avoid loading the full app in master
    from birdhomie.app import setup_logging
    from birdhomie.config import Config
    from birdhomie.scheduler import start_scheduler
    from birdhomie import database as db
    from birdhomie import configure_pytorch

    setup_logging()
    logger.info("Initializing birdhomie in gunicorn master process")

    # Configure PyTorch
    configure_pytorch(logger=logger)

    # Initialize database
    db.init_database()

    # Load config and start scheduler
    try:
        config = Config.from_env()
        _scheduler = start_scheduler(config)
        logger.info("Background scheduler started in master process")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise


def on_exit(server):
    """Called just before exiting gunicorn."""
    global _scheduler
    logger = logging.getLogger("gunicorn.error")

    if _scheduler and _scheduler.running:
        logger.info("Shutting down background scheduler")
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler shutdown complete")


def post_worker_init(worker):
    """Called just after a worker has been initialized.

    This is the ideal place to load ML models once per worker process.
    """
    logger = logging.getLogger("gunicorn.error")
    logger.info(f"Initializing worker {worker.pid}")

    try:
        from birdhomie.config import Config
        from birdhomie.model_cache import preload_models

        config = Config.from_env()
        preload_models(config)
        logger.info(f"Worker {worker.pid} models preloaded successfully")
    except Exception as e:
        logger.error(f"Failed to preload models in worker {worker.pid}: {e}")
        # Don't raise - allow worker to start, models will lazy load if needed


def worker_int(worker):
    """Called when a worker receives SIGINT or SIGQUIT."""
    logger = logging.getLogger("gunicorn.error")
    logger.info(f"Worker {worker.pid} interrupted")


def worker_abort(worker):
    """Called when a worker receives SIGABRT."""
    logger = logging.getLogger("gunicorn.error")
    logger.warning(f"Worker {worker.pid} aborted")
