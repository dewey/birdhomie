"""UniFi Protect integration for downloading motion detection events."""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional
from uiprotect import ProtectApiClient
from uiprotect.data import Event, EventType
from .config import Config
from .constants import INPUT_DIR
from . import database as db

logger = logging.getLogger(__name__)

CURSOR_TYPE_UNIFI_EVENTS = "unifi_events"


def get_sync_cursor() -> Optional[datetime]:
    """Get the last event time from sync cursor.

    Returns:
        The last event time if cursor exists, None otherwise.
    """
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT last_event_time FROM sync_cursors WHERE cursor_type = ?",
            (CURSOR_TYPE_UNIFI_EVENTS,),
        ).fetchone()
        if row:
            return row["last_event_time"]
    return None


def set_sync_cursor(event_time: datetime):
    """Update the sync cursor with the newest event time.

    Args:
        event_time: The timestamp of the newest event fetched.
    """
    with db.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sync_cursors (cursor_type, last_event_time)
            VALUES (?, ?)
            ON CONFLICT(cursor_type) DO UPDATE SET last_event_time = excluded.last_event_time
            """,
            (CURSOR_TYPE_UNIFI_EVENTS, event_time),
        )


def is_fresh_database() -> bool:
    """Check if this is a fresh database with no files yet.

    Returns:
        True if no files exist in the database.
    """
    with db.get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) as count FROM files").fetchone()
        return row["count"] == 0


class UnifiProtectDownloader:
    """Downloads motion detection events from UniFi Protect."""

    def __init__(self, config: Config):
        """Initialize the UniFi Protect downloader.

        Args:
            config: Application configuration
        """
        self.config = config
        self._client: Optional[ProtectApiClient] = None

    async def _get_client(self) -> ProtectApiClient:
        """Get or create the API client."""
        if self._client is None:
            self._client = ProtectApiClient(
                host=self.config.ufp_address,
                port=443,
                username=self.config.ufp_username,
                password=self.config.ufp_password,
                verify_ssl=self.config.ufp_ssl_verify,
            )
            await self._client.update()
            logger.info(
                "unifi_client_connected", extra={"address": self.config.ufp_address}
            )
        return self._client

    async def close(self):
        """Close the API client connection."""
        if self._client:
            try:
                await self._client.async_disconnect()
                logger.info("unifi_client_disconnected")
            except AttributeError:
                pass
            self._client = None

    async def download_recent_events(self, initial_sync_days: int = 30) -> int:
        """Download detection events using cursor-based incremental sync.

        On first run (fresh database), fetches events from the last N days.
        On subsequent runs, fetches from the last known event time.

        Args:
            initial_sync_days: Number of days to look back on fresh database

        Returns:
            Number of events downloaded
        """
        client = await self._get_client()

        # Determine start time based on sync state
        cursor_time = get_sync_cursor()
        end_time = datetime.now()

        if cursor_time:
            # Incremental sync: from cursor to now
            start_time = cursor_time
            sync_type = "incremental"
        elif is_fresh_database():
            # Fresh DB: extended lookback
            start_time = datetime.now() - timedelta(days=initial_sync_days)
            sync_type = "initial"
        else:
            # Existing DB but no cursor (post-migration): use 72h default
            start_time = datetime.now() - timedelta(hours=72)
            sync_type = "migration_fallback"

        logger.info(
            "fetching_unifi_events",
            extra={
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "sync_type": sync_type,
            },
        )

        # Determine event types to fetch
        event_types = []
        if "motion" in self.config.ufp_detection_types:
            event_types.append(EventType.MOTION)

        if not event_types:
            event_types = [EventType.MOTION]

        events = await client.get_events(
            start=start_time,
            end=end_time,
            types=event_types,
        )

        # Filter by camera ID
        filtered_events = [
            e for e in events if e.camera_id == self.config.ufp_camera_id
        ]

        logger.info(
            "unifi_events_found",
            extra={"total": len(events), "filtered": len(filtered_events)},
        )

        downloaded = 0
        newest_event_time = None

        for event in filtered_events:
            try:
                if await self._download_event(client, event):
                    downloaded += 1
                # Track newest event time regardless of download status
                # (already-downloaded events still update cursor)
                if newest_event_time is None or event.start > newest_event_time:
                    newest_event_time = event.start
            except Exception as e:
                logger.error(
                    "event_download_failed",
                    extra={"event_id": event.id, "error": str(e)},
                    exc_info=True,
                )

        # Update cursor with newest event time
        if newest_event_time:
            set_sync_cursor(newest_event_time)
            logger.info(
                "sync_cursor_updated",
                extra={"newest_event_time": newest_event_time.isoformat()},
            )

        return downloaded

    async def _download_event(self, client: ProtectApiClient, event: Event) -> bool:
        """Download a single event's video clip.

        Args:
            client: API client
            event: Event to download

        Returns:
            True if downloaded, False if already exists
        """
        event_start = event.start
        event_end = event.end if event.end else event_start

        # Check if already exists in database
        with db.get_connection() as conn:
            existing = conn.execute(
                """
                SELECT id FROM files
                WHERE source_event_id = ?
            """,
                (event.id,),
            ).fetchone()

            if existing:
                logger.debug("event_already_in_database", extra={"event_id": event.id})
                return False

        # Create filename
        filename = f"unifi_{event_start.strftime('%Y-%m-%d_%H-%M-%S')}.mp4"
        output_path = INPUT_DIR / filename

        # Check if file already exists on disk
        if output_path.exists():
            logger.debug(
                "event_file_already_exists", extra={"video_filename": filename}
            )
            return False

        logger.info(
            "downloading_event",
            extra={"event_id": event.id, "video_filename": filename},
        )

        INPUT_DIR.mkdir(parents=True, exist_ok=True)

        try:
            video_data = await event.get_video()
            if not video_data:
                logger.warning("no_video_data", extra={"event_id": event.id})
                return False

            output_path.write_bytes(video_data)

            # Calculate file hash
            file_hash = hashlib.sha256(video_data).hexdigest()

            # Calculate duration
            duration = (event_end - event_start).total_seconds() if event_end else None

            # Insert into database
            with db.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO files
                    (file_path, file_hash, source_event_id, event_start, event_end,
                     duration_seconds, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending')
                    ON CONFLICT(file_path) DO NOTHING
                """,
                    (
                        str(output_path),
                        file_hash,
                        event.id,
                        event_start,
                        event_end,
                        duration,
                    ),
                )

            logger.info(
                "event_downloaded",
                extra={
                    "video_filename": filename,
                    "size_bytes": len(video_data),
                    "duration": duration,
                },
            )

            return True

        except Exception as e:
            logger.error(
                "video_download_failed",
                extra={
                    "event_id": event.id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            return False


def download_unifi_events_sync(config: Config, initial_sync_days: int = 30) -> int:
    """Download UniFi Protect events synchronously.

    Uses cursor-based incremental sync. On first run (fresh database),
    fetches events from the last N days. On subsequent runs, fetches
    from the last known event time.

    Args:
        config: Application configuration
        initial_sync_days: Number of days to look back on fresh database

    Returns:
        Number of events downloaded
    """
    downloader = UnifiProtectDownloader(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        count = loop.run_until_complete(
            downloader.download_recent_events(initial_sync_days=initial_sync_days)
        )
        loop.run_until_complete(downloader.close())
        return count
    finally:
        loop.close()
