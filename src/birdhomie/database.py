"""Database layer with migrations and connection management."""

import sqlite3
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator
from .constants import DB_PATH, MIGRATIONS_DIR

logger = logging.getLogger(__name__)

# Register adapters and converters for datetime (required for Python 3.12+)
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
sqlite3.register_converter("timestamp", lambda b: datetime.fromisoformat(b.decode()))
sqlite3.register_converter("datetime", lambda b: datetime.fromisoformat(b.decode()))


def get_db_path() -> Path:
    """Get the database path."""
    return DB_PATH


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Context manager for database connections with optimizations."""
    conn = sqlite3.connect(
        get_db_path(), detect_types=sqlite3.PARSE_DECLTYPES, timeout=30.0
    )
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for concurrent reads/writes
    conn.execute("PRAGMA journal_mode=WAL")

    # Performance optimizations
    conn.execute("PRAGMA synchronous=NORMAL")  # Faster commits, safe with WAL
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    conn.execute("PRAGMA temp_store=MEMORY")  # Keep temp tables in memory
    conn.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_migrations(db_path: str = None, migrations_dir: str = None):
    """Apply any pending migrations in order with transaction safety."""
    if db_path is None:
        db_path = str(get_db_path())
    if migrations_dir is None:
        migrations_dir = str(MIGRATIONS_DIR)

    # Ensure data directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)

    # Create tracking table with checksum
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Get already applied versions
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}

    # Find and sort migration files (exclude rollback files)
    migration_files = sorted(
        [f for f in Path(migrations_dir).glob("*.sql") if "rollback" not in f.name]
    )

    for migration_file in migration_files:
        version = int(migration_file.name.split("_")[0])
        if version not in applied:
            logger.info("applying_migration", extra={"file": migration_file.name})

            sql = migration_file.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()

            try:
                # Execute in transaction for atomicity
                conn.execute("BEGIN TRANSACTION")
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version, filename, checksum) VALUES (?, ?, ?)",
                    (version, migration_file.name, checksum),
                )
                conn.commit()
                logger.info("migration_applied", extra={"version": version})
            except Exception as e:
                conn.rollback()
                logger.error(
                    "migration_failed", extra={"version": version, "error": str(e)}
                )
                raise

    conn.close()


def init_database():
    """Initialize database and run migrations."""
    logger.info("initializing_database", extra={"path": str(get_db_path())})

    # Ensure directories exist
    get_db_path().parent.mkdir(parents=True, exist_ok=True)

    # Run migrations
    run_migrations()

    logger.info("database_initialized")


def get_db_size() -> str:
    """Get database size as formatted string."""
    db_path = get_db_path()
    if not db_path.exists():
        return "0 B"

    size_bytes = db_path.stat().st_size

    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0

    return f"{size_bytes:.1f} TB"


if __name__ == "__main__":
    import sys

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if len(sys.argv) > 1:
        if sys.argv[1] == "init":
            init_database()
        elif sys.argv[1] == "migrate":
            run_migrations()
        else:
            print(f"Unknown command: {sys.argv[1]}")
            print("Usage: python -m birdhomie.database [init|migrate]")
            sys.exit(1)
    else:
        print("Usage: python -m birdhomie.database [init|migrate]")
        sys.exit(1)
