"""Flask web application for birdhomie."""

import logging
from datetime import datetime
from pathlib import Path
from io import BytesIO
from flask import (
    Flask,
    render_template,
    g,
    request,
    send_from_directory,
    redirect,
    url_for,
    flash,
    jsonify,
    send_file,
    Response,
)
from flask_babel import Babel, _
from markupsafe import Markup
from PIL import Image
from .config import Config
from .constants import LOGS_DIR, DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, DATA_DIR
from . import database as db


# Setup logging
def setup_logging():
    """Configure structured logging for the application."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOGS_DIR / "birdhomie.log"),
            logging.StreamHandler(),
        ],
    )


setup_logging()
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Load configuration
try:
    config = Config.from_env()
    app.config["SECRET_KEY"] = config.secret_key
    app.config["DEBUG"] = config.flask_debug
except ValueError as e:
    logger.error("config_validation_failed", extra={"error": str(e)})
    raise

# Initialize Babel for i18n
babel = Babel(app)


def get_locale():
    """Return the current language with fallback."""
    # Check cookie
    lang = request.cookies.get("lang")
    if lang in SUPPORTED_LANGUAGES:
        return lang

    # Check Accept-Language header
    lang = request.accept_languages.best_match(SUPPORTED_LANGUAGES.keys())
    if lang:
        return lang

    # Default
    return DEFAULT_LANGUAGE


babel.init_app(app, locale_selector=get_locale)


@app.template_filter("format_datetime")
def format_datetime_filter(dt, format_type="full", show_tooltip=True):
    """
    Format datetime based on locale and format type.

    Args:
        dt: Datetime object or ISO string
        format_type: 'date', 'time', 'datetime', or 'full'
        show_tooltip: If True, wrap in span with title attribute showing full timestamp

    Returns:
        Formatted datetime string or HTML with tooltip
    """
    if not dt:
        return "N/A"

    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)

    # Convert UTC datetime to local time for display
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)

    locale = g.get("locale", "en")

    # Generate full timestamp for tooltip
    if locale == "de":
        full_timestamp = dt.strftime("%-d. %B %Y, %H:%M:%S")
    else:
        full_timestamp = dt.strftime("%B %-d, %Y, %-I:%M:%S %p")

    # Format display text
    if format_type == "date":
        # Short date: Jan 7, 2026 (en) or 7. Jan. 2026 (de)
        if locale == "de":
            display = dt.strftime("%-d. %b. %Y")
        else:
            display = dt.strftime("%b %-d, %Y")

    elif format_type == "time":
        # Time only
        if locale == "de":
            display = dt.strftime("%H:%M")  # 24h format
        else:
            display = dt.strftime("%-I:%M %p")  # 12h format with am/pm

    elif format_type == "datetime":
        # Full datetime
        if locale == "de":
            display = dt.strftime("%-d. %b. %Y, %H:%M")
        else:
            display = dt.strftime("%b %-d, %Y, %-I:%M %p")

    else:  # 'full' with seconds
        if locale == "de":
            display = dt.strftime("%-d. %b. %Y, %H:%M:%S")
        else:
            display = dt.strftime("%b %-d, %Y, %-I:%M:%S %p")

    # Wrap with tooltip if requested
    if show_tooltip and format_type != "full":
        return Markup(
            f'<span title="{full_timestamp}" class="cursor-help">{display}</span>'
        )

    return display


@app.template_filter("format_time_ago")
def format_time_ago_filter(dt):
    """
    Format datetime as relative time with tooltip showing full timestamp.
    Always includes hover tooltip with full timestamp.

    Returns:
        HTML string with relative time and tooltip
    """
    if not dt:
        return "N/A"

    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)

    # Convert UTC datetime to local time for display and comparison
    if dt.tzinfo is not None:
        # Convert to local time, then make naive for comparison with datetime.now()
        dt = dt.astimezone().replace(tzinfo=None)

    now = datetime.now()
    diff = now - dt

    locale = g.get("locale", "en")

    # Generate full timestamp for tooltip
    if locale == "de":
        full_timestamp = dt.strftime("%-d. %B %Y, %H:%M:%S")
    else:
        full_timestamp = dt.strftime("%B %-d, %Y, %-I:%M:%S %p")

    # Generate relative time display
    if diff.days > 0:
        if diff.days == 1:
            display = "gestern" if locale == "de" else "yesterday"
        elif diff.days < 7:
            if locale == "de":
                display = f"vor {diff.days} Tagen"
            else:
                display = f"{diff.days} days ago"
        elif diff.days < 30:
            weeks = diff.days // 7
            if locale == "de":
                display = f"vor {weeks} {'Woche' if weeks == 1 else 'Wochen'}"
            else:
                display = f"{weeks} {'week' if weeks == 1 else 'weeks'} ago"
        else:
            months = diff.days // 30
            if locale == "de":
                display = f"vor {months} {'Monat' if months == 1 else 'Monaten'}"
            else:
                display = f"{months} {'month' if months == 1 else 'months'} ago"
    else:
        hours = diff.seconds // 3600
        if hours > 0:
            if locale == "de":
                display = f"vor {hours} {'Stunde' if hours == 1 else 'Stunden'}"
            else:
                display = f"{hours} {'hour' if hours == 1 else 'hours'} ago"
        else:
            minutes = diff.seconds // 60
            if minutes > 0:
                if locale == "de":
                    display = f"vor {minutes} {'Minute' if minutes == 1 else 'Minuten'}"
                else:
                    display = f"{minutes} {'minute' if minutes == 1 else 'minutes'} ago"
            else:
                display = "gerade eben" if locale == "de" else "just now"

    # Always return with tooltip
    return Markup(
        f'<span title="{full_timestamp}" class="cursor-help">{display}</span>'
    )


@app.before_request
def before_request():
    """Set up request context."""
    g.locale = get_locale()


@app.route("/")
def dashboard():
    """Main dashboard."""
    period = request.args.get("period", "month")

    # Calculate date range
    if period == "week":
        date_filter = "DATE('now', '-7 days')"
    elif period == "month":
        date_filter = "DATE('now', '-30 days')"
    else:  # today
        date_filter = "DATE('now', '-1 day')"

    with db.get_connection() as conn:
        species = conn.execute(f"""
            SELECT
                t.taxon_id,
                t.scientific_name,
                COALESCE(t.common_name_{g.locale}, t.scientific_name) as name,
                COUNT(DISTINCT v.id) as visit_count,
                si.local_path as image_path,
                si.attribution
            FROM visits v
            JOIN files f ON v.file_id = f.id
            JOIN inaturalist_taxa t ON COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) = t.taxon_id
            LEFT JOIN species_images si ON t.taxon_id = si.taxon_id AND si.is_default = 1
            WHERE f.event_start >= {date_filter}
                AND v.deleted_at IS NULL
            GROUP BY t.taxon_id
            ORDER BY visit_count DESC
        """).fetchall()

        stats = conn.execute(f"""
            SELECT
                COUNT(DISTINCT v.id) as total_visits,
                COUNT(DISTINCT t.taxon_id) as unique_species,
                COUNT(DISTINCT d.id) as total_detections
            FROM visits v
            JOIN files f ON v.file_id = f.id
            JOIN inaturalist_taxa t ON COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) = t.taxon_id
            LEFT JOIN detections d ON v.id = d.visit_id
            WHERE f.event_start >= {date_filter}
                AND v.deleted_at IS NULL
        """).fetchone()

        most_active_hour_row = conn.execute(f"""
            SELECT CAST(strftime('%H', f.event_start) AS INTEGER) as hour
            FROM visits v
            JOIN files f ON v.file_id = f.id
            WHERE f.event_start >= {date_filter}
                AND v.deleted_at IS NULL
            GROUP BY hour
            ORDER BY COUNT(*) DESC
            LIMIT 1
        """).fetchone()

        most_popular_day_row = conn.execute(f"""
            SELECT CAST(strftime('%w', f.event_start) AS INTEGER) as day_of_week
            FROM visits v
            JOIN files f ON v.file_id = f.id
            WHERE f.event_start >= {date_filter}
                AND v.deleted_at IS NULL
            GROUP BY day_of_week
            ORDER BY COUNT(*) DESC
            LIMIT 1
        """).fetchone()

        stats = dict(stats) if stats else {}
        stats["most_active_hour"] = (
            most_active_hour_row["hour"] if most_active_hour_row else None
        )

        day_names = {
            0: _("Sunday"),
            1: _("Monday"),
            2: _("Tuesday"),
            3: _("Wednesday"),
            4: _("Thursday"),
            5: _("Friday"),
            6: _("Saturday"),
        }
        stats["most_popular_day"] = (
            most_popular_day_row["day_of_week"] if most_popular_day_row else None
        )
        stats["most_popular_day_name"] = (
            day_names.get(stats["most_popular_day"], _("N/A"))
            if stats["most_popular_day"] is not None
            else _("N/A")
        )

        # Calculate longest visiting streaks for all species
        streak_data = conn.execute(f"""
            WITH visit_dates AS (
                SELECT DISTINCT
                    COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) as taxon_id,
                    DATE(f.event_start) as visit_date
                FROM visits v
                JOIN files f ON v.file_id = f.id
                WHERE f.event_start >= {date_filter}
                    AND v.deleted_at IS NULL
            ),
            dates_with_prev AS (
                SELECT
                    taxon_id,
                    visit_date,
                    LAG(visit_date) OVER (PARTITION BY taxon_id ORDER BY visit_date) as prev_date,
                    julianday(visit_date) - julianday(LAG(visit_date) OVER (PARTITION BY taxon_id ORDER BY visit_date)) as days_diff
                FROM visit_dates
            ),
            streak_groups AS (
                SELECT
                    taxon_id,
                    visit_date,
                    SUM(CASE WHEN days_diff = 1 OR days_diff IS NULL THEN 0 ELSE 1 END)
                        OVER (PARTITION BY taxon_id ORDER BY visit_date) as streak_group
                FROM dates_with_prev
            ),
            streak_lengths AS (
                SELECT
                    taxon_id,
                    streak_group,
                    COUNT(*) as streak_days
                FROM streak_groups
                GROUP BY taxon_id, streak_group
            ),
            max_streaks AS (
                SELECT
                    taxon_id,
                    MAX(streak_days) as longest_streak
                FROM streak_lengths
                GROUP BY taxon_id
            )
            SELECT
                t.taxon_id,
                COALESCE(t.common_name_{g.locale}, t.scientific_name) as species_name,
                ms.longest_streak
            FROM max_streaks ms
            JOIN inaturalist_taxa t ON ms.taxon_id = t.taxon_id
            ORDER BY ms.longest_streak DESC, species_name ASC
            LIMIT 5
        """).fetchall()

    return render_template(
        "dashboard.html",
        species=species,
        period=period,
        stats=stats,
        streak_data=streak_data,
    )


@app.route("/api/stats/hourly-activity")
def hourly_activity():
    """Get hourly activity data for chart."""
    period = request.args.get("period", "month")

    if period == "week":
        date_filter = "DATE('now', '-7 days')"
    elif period == "month":
        date_filter = "DATE('now', '-30 days')"
    else:
        date_filter = "DATE('now', '-1 day')"

    with db.get_connection() as conn:
        hourly_data = conn.execute(f"""
            SELECT
                CAST(strftime('%H', f.event_start) AS INTEGER) as hour,
                COUNT(DISTINCT v.id) as visit_count
            FROM visits v
            JOIN files f ON v.file_id = f.id
            WHERE f.event_start >= {date_filter}
                AND v.deleted_at IS NULL
            GROUP BY hour
            ORDER BY hour
        """).fetchall()

    hours = list(range(24))
    visit_counts = [0] * 24
    for row in hourly_data:
        visit_counts[row["hour"]] = row["visit_count"]

    return jsonify({"labels": hours, "data": visit_counts})


@app.route("/species")
def species_list():
    """List all species."""
    with db.get_connection() as conn:
        species = conn.execute(f"""
            SELECT
                t.taxon_id,
                t.scientific_name,
                COALESCE(t.common_name_{g.locale}, t.scientific_name) as name,
                COUNT(DISTINCT v.id) as visit_count,
                MAX(f.event_start) as last_seen,
                si.local_path as image_path
            FROM inaturalist_taxa t
            LEFT JOIN visits v ON t.taxon_id IN (v.inaturalist_taxon_id, v.override_taxon_id) AND v.deleted_at IS NULL
            LEFT JOIN files f ON v.file_id = f.id
            LEFT JOIN species_images si ON t.taxon_id = si.taxon_id AND si.is_default = 1
            GROUP BY t.taxon_id
            HAVING visit_count > 0
            ORDER BY visit_count DESC
        """).fetchall()

    return render_template("species_list.html", species=species)


@app.route("/species/<int:taxon_id>")
def species_detail(taxon_id):
    """Species detail page."""
    with db.get_connection() as conn:
        # Get species info
        species = conn.execute(
            """
            SELECT
                t.*,
                si.local_path as image_path,
                si.attribution,
                wp.extract as wikipedia_excerpt,
                wp.url as wikipedia_url,
                COUNT(DISTINCT v.id) as total_visits,
                MIN(f.event_start) as first_seen,
                MAX(f.event_start) as last_seen
            FROM inaturalist_taxa t
            LEFT JOIN species_images si ON t.taxon_id = si.taxon_id AND si.is_default = 1
            LEFT JOIN wikipedia_pages wp ON t.wikidata_qid = wp.wikidata_qid
                AND wp.language_code = ?
            LEFT JOIN visits v ON t.taxon_id IN (v.inaturalist_taxon_id, v.override_taxon_id) AND v.deleted_at IS NULL
            LEFT JOIN files f ON v.file_id = f.id
            WHERE t.taxon_id = ?
            GROUP BY t.taxon_id
        """,
            (g.locale, taxon_id),
        ).fetchone()

        if not species:
            return "Species not found", 404

        # Get recent visits
        visits = conn.execute(
            """
            SELECT
                v.id,
                v.species_confidence,
                v.detection_count,
                v.cover_detection_id,
                f.event_start,
                d.crop_path as best_crop
            FROM visits v
            JOIN files f ON v.file_id = f.id
            LEFT JOIN detections d ON d.id = v.cover_detection_id
            WHERE COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) = ?
                AND v.deleted_at IS NULL
            ORDER BY f.event_start DESC
            LIMIT 20
        """,
            (taxon_id,),
        ).fetchall()

        recent_crops = conn.execute(
            """
            SELECT
                d.id as detection_id,
                d.crop_path,
                d.detection_confidence,
                d.annotation_source,
                COALESCE(d.reviewed_at, d.annotated_at) as cache_key,
                v.id as visit_id,
                v.species_confidence,
                f.event_start
            FROM detections d
            JOIN visits v ON d.visit_id = v.id
            JOIN files f ON v.file_id = f.id
            WHERE COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) = ?
                AND v.deleted_at IS NULL
                AND d.id = v.cover_detection_id
                AND d.crop_path IS NOT NULL
                AND (d.annotation_source IS NULL OR d.annotation_source != 'no_face')
            ORDER BY f.event_start DESC
            LIMIT 5
        """,
            (taxon_id,),
        ).fetchall()

        return render_template(
            "species_detail.html",
            species=species,
            visits=visits,
            recent_crops=recent_crops,
        )


@app.route("/visits/<int:visit_id>")
def visit_detail(visit_id):
    """Visit detail page with video player and detection crops."""
    with db.get_connection() as conn:
        # Get visit info with file and species data
        visit = conn.execute(
            f"""
            SELECT
                v.*,
                t.taxon_id,
                t.scientific_name,
                COALESCE(t.common_name_{g.locale}, t.scientific_name) as species_name,
                t.common_name_en,
                t.common_name_de,
                f.id as file_id,
                f.file_path,
                f.output_dir,
                f.event_start,
                f.duration_seconds,
                f.status as file_status
            FROM visits v
            JOIN files f ON v.file_id = f.id
            JOIN inaturalist_taxa t ON COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) = t.taxon_id
            WHERE v.id = ?
        """,
            (visit_id,),
        ).fetchone()

        if not visit:
            return "Visit not found", 404

        # Check if visit is soft-deleted
        if visit["deleted_at"] is not None:
            flash(_("This visit has been deleted"), "warning")
            return redirect(url_for("dashboard"))

        # Get all detections for this visit
        detections = conn.execute(
            """
            SELECT
                id,
                frame_number,
                frame_timestamp,
                detection_confidence,
                detection_confidence_model,
                species_confidence,
                species_confidence_model,
                crop_path,
                bbox_x1, bbox_y1, bbox_x2, bbox_y2,
                annotation_source
            FROM detections
            WHERE visit_id = ?
            ORDER BY frame_number
        """,
            (visit_id,),
        ).fetchall()

        # Get all known species for correction dropdown
        all_species = conn.execute(f"""
            SELECT
                taxon_id,
                scientific_name,
                COALESCE(common_name_{g.locale}, scientific_name) as name
            FROM inaturalist_taxa
            ORDER BY name
        """).fetchall()

        # Determine if file is video or image
        file_path = visit["file_path"]
        is_video = file_path.lower().endswith((".mp4", ".avi", ".mov", ".mkv"))

        # Check video availability
        annotated_path = None
        video_available = False
        file_status = visit["file_status"]

        if is_video and file_status == "success":
            output_dir = visit["output_dir"].replace(str(DATA_DIR) + "/", "")
            annotated_path = f"{output_dir}/annotated.mp4"
            annotated_full_path = (
                DATA_DIR / "output" / str(visit["file_id"]) / "annotated.mp4"
            )
            video_available = annotated_full_path.exists()

    return render_template(
        "visit_detail.html",
        visit=visit,
        detections=detections,
        all_species=all_species,
        is_video=is_video,
        annotated_path=annotated_path,
        video_available=video_available,
        file_status=file_status,
    )


@app.route("/visits/<int:visit_id>/correct", methods=["POST"])
def correct_visit_species(visit_id):
    """Correct species identification for a visit."""
    from .inaturalist import parse_inaturalist_url, get_or_create_taxon_by_id

    new_taxon_id = request.form.get("taxon_id", type=int)
    inaturalist_url = request.form.get("inaturalist_url", "").strip()

    # Handle iNaturalist URL if provided
    if inaturalist_url:
        taxon_id_from_url = parse_inaturalist_url(inaturalist_url)

        if not taxon_id_from_url:
            flash(
                "Invalid iNaturalist URL. Please use format: https://www.inaturalist.org/taxa/12345",
                "error",
            )
            return redirect(url_for("visit_detail", visit_id=visit_id))

        # Fetch and create species if not exists
        new_taxon_id = get_or_create_taxon_by_id(taxon_id_from_url)

        if not new_taxon_id:
            flash(
                "Failed to fetch species from iNaturalist. Please try again.", "error"
            )
            return redirect(url_for("visit_detail", visit_id=visit_id))

        flash(
            f"Species fetched from iNaturalist (taxon_id: {new_taxon_id}) and visit updated!",
            "success",
        )
    elif not new_taxon_id:
        flash("Please select a species or provide an iNaturalist URL", "error")
        return redirect(url_for("visit_detail", visit_id=visit_id))

    # Update visit with override taxon
    with db.get_connection() as conn:
        conn.execute(
            """
            UPDATE visits
            SET override_taxon_id = ?,
                corrected_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (new_taxon_id, visit_id),
        )
        conn.commit()

    if not inaturalist_url:
        flash("Species corrected successfully", "success")

    return redirect(url_for("visit_detail", visit_id=visit_id))


@app.route("/files")
def files_list():
    """List all files."""
    with db.get_connection() as conn:
        files = conn.execute("""
            SELECT * FROM files
            ORDER BY event_start DESC
        """).fetchall()

    return render_template("files_list.html", files=files)


@app.route("/api/visits/<int:visit_id>/set-cover/<int:detection_id>", methods=["POST"])
def set_visit_cover(visit_id, detection_id):
    """Set a detection as the cover image for a visit."""
    with db.get_connection() as conn:
        detection = conn.execute(
            """
            SELECT id FROM detections
            WHERE id = ? AND visit_id = ?
        """,
            (detection_id, visit_id),
        ).fetchone()

        if not detection:
            return jsonify(
                {
                    "success": False,
                    "error": "Detection not found or does not belong to visit",
                }
            ), 404

        conn.execute(
            """
            UPDATE visits
            SET cover_detection_id = ?
            WHERE id = ?
        """,
            (detection_id, visit_id),
        )
        conn.commit()

    return jsonify({"success": True})


@app.route("/files/<int:file_id>")
def file_detail(file_id):
    """File detail page showing all content from this file's output folder."""
    with db.get_connection() as conn:
        file = conn.execute(
            """
            SELECT
                id,
                file_path,
                event_start,
                duration_seconds,
                output_dir,
                status,
                duplicate_of_file_id
            FROM files
            WHERE id = ?
        """,
            (file_id,),
        ).fetchone()

        if not file:
            return "File not found", 404

        visits = conn.execute(
            f"""
            SELECT
                v.id,
                v.species_confidence,
                v.detection_count,
                t.taxon_id,
                COALESCE(t.common_name_{g.locale}, t.scientific_name) as species_name,
                t.scientific_name
            FROM visits v
            JOIN inaturalist_taxa t ON COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) = t.taxon_id
            WHERE v.file_id = ?
                AND v.deleted_at IS NULL
            ORDER BY v.species_confidence DESC
        """,
            (file_id,),
        ).fetchall()

        all_detections = conn.execute(
            """
            SELECT
                d.id as detection_id,
                d.crop_path,
                d.detection_confidence,
                d.frame_number,
                d.frame_timestamp,
                d.annotation_source,
                COALESCE(d.reviewed_at, d.annotated_at) as cache_key,
                v.id as visit_id,
                v.cover_detection_id as display_detection_id
            FROM detections d
            JOIN visits v ON d.visit_id = v.id
            WHERE v.file_id = ?
                AND v.deleted_at IS NULL
                AND d.crop_path IS NOT NULL
            ORDER BY d.frame_number ASC
        """,
            (file_id,),
        ).fetchall()

        # Get available files for merge dropdown (excluding current file)
        available_files = conn.execute(
            """
            SELECT
                id,
                file_path,
                event_start,
                duration_seconds,
                status
            FROM files
            WHERE id != ?
            ORDER BY event_start DESC
            LIMIT 100
        """,
            (file_id,),
        ).fetchall()

        is_video = file["file_path"].lower().endswith((".mp4", ".avi", ".mov", ".mkv"))

        # Check video availability
        annotated_path = None
        video_available = False
        file_status = file["status"]

        if is_video and file_status == "success":
            output_dir = file["output_dir"].replace(str(DATA_DIR) + "/", "")
            annotated_path = f"{output_dir}/annotated.mp4"
            annotated_full_path = DATA_DIR / "output" / str(file_id) / "annotated.mp4"
            video_available = annotated_full_path.exists()

    return render_template(
        "file_detail.html",
        file=file,
        visits=visits,
        detections=all_detections,
        available_files=available_files,
        is_video=is_video,
        annotated_path=annotated_path,
        video_available=video_available,
        file_status=file_status,
    )


@app.route("/files/<int:file_id>/unignore", methods=["POST"])
def unignore_file(file_id):
    """Remove ignored status from a file and mark it for processing."""
    with db.get_connection() as conn:
        conn.execute(
            """
            UPDATE files
            SET status = 'pending',
                duplicate_of_file_id = NULL
            WHERE id = ?
        """,
            (file_id,),
        )

    return redirect(url_for("file_detail", file_id=file_id))


@app.route("/files/<int:file_id>/merge", methods=["POST"])
def merge_file(file_id):
    """Merge a file into another file.

    This marks the source file as ignored, soft-deletes its visits,
    and keeps the file on disk for potential re-processing.
    """
    target_id = request.form.get("target_id", type=int)

    if not target_id:
        flash(_("Target file ID is required"), "error")
        return redirect(url_for("file_detail", file_id=file_id))

    if target_id == file_id:
        flash(_("Cannot merge a file into itself"), "error")
        return redirect(url_for("file_detail", file_id=file_id))

    with db.get_connection() as conn:
        # Verify both files exist
        source = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        target = conn.execute(
            "SELECT * FROM files WHERE id = ?", (target_id,)
        ).fetchone()

        if not source or not target:
            flash(_("One or both files not found"), "error")
            return redirect(url_for("files_list"))

        # Mark source file as ignored
        conn.execute(
            """
            UPDATE files
            SET status = 'ignored',
                duplicate_of_file_id = ?
            WHERE id = ?
        """,
            (target_id, file_id),
        )

        # Soft delete all visits from the source file
        conn.execute(
            """
            UPDATE visits
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE file_id = ? AND deleted_at IS NULL
        """,
            (file_id,),
        )

        logger.info(
            "file_merged",
            extra={"source_file_id": file_id, "target_file_id": target_id},
        )

        flash(_("File merged successfully"), "success")

    return redirect(url_for("file_detail", file_id=target_id))


@app.route("/data/<path:filename>")
def serve_data(filename):
    """Serve files from data directory."""
    data_dir = Path(__file__).parent.parent.parent / "data"
    return send_from_directory(data_dir, filename)


@app.route("/tasks")
def tasks_list():
    """List all task runs."""
    with db.get_connection() as conn:
        # Get all recent tasks, showing running tasks first
        # Format timestamps as ISO 8601 with 'Z' suffix to indicate UTC
        tasks = conn.execute("""
            SELECT
                id,
                task_type,
                status,
                started_at || 'Z' as started_at,
                CASE WHEN completed_at IS NOT NULL THEN completed_at || 'Z' ELSE NULL END as completed_at,
                duration_seconds,
                items_processed,
                items_failed,
                error_message,
                hostname,
                pid
            FROM task_runs
            ORDER BY
                CASE status
                    WHEN 'running' THEN 0
                    ELSE 1
                END,
                COALESCE(completed_at, started_at) DESC
            LIMIT 100
        """).fetchall()

    # Pass scheduler configuration
    schedule_info = {
        "unifi_download_interval": config.ufp_download_interval_minutes,
        "file_processor_interval": config.processor_interval_minutes,
        "face_annotation_interval": 10,  # Hardcoded in scheduler
    }

    return render_template("tasks_list.html", tasks=tasks, schedule=schedule_info)


@app.route("/tasks/api")
def tasks_api():
    """API endpoint to get task runs as JSON."""
    with db.get_connection() as conn:
        # Get all recent tasks, showing running tasks first
        # Format timestamps as ISO 8601 with 'Z' suffix to indicate UTC
        tasks = conn.execute("""
            SELECT
                id,
                task_type,
                status,
                started_at || 'Z' as started_at,
                CASE WHEN completed_at IS NOT NULL THEN completed_at || 'Z' ELSE NULL END as completed_at,
                duration_seconds,
                items_processed,
                items_failed,
                error_message,
                hostname,
                pid
            FROM task_runs
            ORDER BY
                CASE status
                    WHEN 'running' THEN 0
                    ELSE 1
                END,
                COALESCE(completed_at, started_at) DESC
            LIMIT 100
        """).fetchall()

    return jsonify([dict(task) for task in tasks])


@app.route("/metrics")
def prometheus_metrics():
    """Prometheus metrics endpoint for scraping."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from . import metrics as m

    m.update_gauges()
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/tasks/trigger/<task_type>", methods=["POST"])
def trigger_task(task_type):
    """Manually trigger a background task."""
    from .scheduler import (
        process_files_task,
        download_unifi_task,
        face_annotation_task,
        regenerate_thumbnails_task,
    )
    import threading

    def run_task():
        try:
            if task_type == "file_processor":
                process_files_task(config)
            elif task_type == "unifi_download":
                download_unifi_task(config)
            elif task_type == "face_annotation":
                face_annotation_task(config)
            elif task_type == "regenerate_thumbnails":
                regenerate_thumbnails_task(config)
            else:
                logger.error("unknown_task_type", extra={"task_type": task_type})
        except Exception as e:
            logger.error(
                "manual_task_failed", extra={"task_type": task_type, "error": str(e)}
            )

    # Run in background thread
    thread = threading.Thread(target=run_task)
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started", "task_type": task_type})


@app.route("/settings")
def settings():
    """Settings page."""
    settings_data = {
        "unifi": {
            "address": config.ufp_address,
            "camera_id": config.ufp_camera_id[:10] + "...",
            "detection_types": config.ufp_detection_types,
            "download_interval": config.ufp_download_interval_minutes,
            "ssl_verify": config.ufp_ssl_verify,
        },
        "video": {
            "frame_skip": config.frame_skip,
        },
        "detection": {
            "detection_model": "YOLOv8m",
            "classification_model": "BioCLIP-2",
            "min_detection_confidence": config.min_detection_confidence,
            "min_species_confidence": config.min_species_confidence,
        },
        "tasks": {
            "processor_interval": config.processor_interval_minutes,
            "file_retention_days": config.file_retention_days,
        },
        "database": {
            "type": "SQLite with WAL mode",
            "path": "data/birdhomie.db",
            "size": db.get_db_size(),
        },
    }

    return render_template("settings.html", settings=settings_data)


def calculate_thumbnail_center(detection, img_width, img_height):
    """
    Calculate optimal center point for thumbnail crop using face bbox.

    Prioritizes showing the top portion of face (where eyes/beak are)
    rather than geometric center.

    Returns: (center_x, center_y) in crop-relative coordinates
    """
    if detection["face_bbox_x1"] is not None:
        # Face bbox is stored in absolute (full-frame) coordinates
        # Convert to crop-relative by subtracting crop offset
        face_crop_x1 = detection["face_bbox_x1"] - detection["bbox_x1"]
        face_crop_y1 = detection["face_bbox_y1"] - detection["bbox_y1"]
        face_crop_x2 = detection["face_bbox_x2"] - detection["bbox_x1"]
        face_crop_y2 = detection["face_bbox_y2"] - detection["bbox_y1"]

        # Center horizontally
        face_center_x = (face_crop_x1 + face_crop_x2) // 2

        # Vertically: bias toward upper portion (where eyes/beak are) while showing context
        face_height = face_crop_y2 - face_crop_y1
        face_center_y = face_crop_y1 + int(face_height * 0.40)

        return (face_center_x, face_center_y)

    # Fallback: use image center
    return (img_width // 2, img_height // 2)


@app.route("/thumbnail/<int:detection_id>/<int:size>")
def generate_thumbnail(detection_id: int, size: int):
    """Generate thumbnail centered on face bbox."""
    with db.get_connection() as conn:
        detection = conn.execute(
            """
            SELECT crop_path,
                   bbox_x1, bbox_y1, bbox_x2, bbox_y2,
                   face_bbox_x1, face_bbox_y1, face_bbox_x2, face_bbox_y2
            FROM detections
            WHERE id = ?
        """,
            (detection_id,),
        ).fetchone()

    if not detection or not detection["crop_path"]:
        return "Not found", 404

    # Construct full path to crop
    crop_path = DATA_DIR / "output" / detection["crop_path"]
    if not crop_path.exists():
        return "Image not found", 404

    # Load image
    img = Image.open(crop_path)

    # Calculate center point using face bbox (or fallback)
    center_x, center_y = calculate_thumbnail_center(detection, img.width, img.height)

    # Create square thumbnail centered on calculated point
    thumb_size = (size, size)

    # Use larger crop area to show more context (3.5x zoom factor)
    # This ensures the face is the focal point but shows more of the bird
    crop_size = int(size * 3.5)

    # Calculate crop box
    half_size = crop_size // 2
    left = max(0, center_x - half_size)
    top = max(0, center_y - half_size)
    right = min(img.width, left + crop_size)
    bottom = min(img.height, top + crop_size)

    # Adjust if we hit edges
    if right - left < crop_size:
        left = max(0, right - crop_size)
    if bottom - top < crop_size:
        top = max(0, bottom - crop_size)

    # Crop and resize
    thumb = img.crop((left, top, right, bottom))
    thumb = thumb.resize(thumb_size, Image.Resampling.LANCZOS)

    # Serve image
    img_io = BytesIO()
    thumb.save(img_io, "JPEG", quality=85)
    img_io.seek(0)

    return send_file(img_io, mimetype="image/jpeg")


@app.route("/labeling")
def labeling():
    """Labeling interface for reviewing face annotations."""
    detection_id = request.args.get("id", type=int)
    return_url = request.args.get("return_url", "")

    with db.get_connection() as conn:
        if detection_id:
            # Get specific detection by ID
            current = conn.execute(
                f"""
                SELECT d.id, d.crop_path, d.bbox_x1, d.bbox_y1, d.bbox_x2, d.bbox_y2,
                       d.face_bbox_x1, d.face_bbox_y1, d.face_bbox_x2, d.face_bbox_y2,
                       d.annotation_source, d.detection_confidence, d.frame_timestamp,
                       t.scientific_name,
                       COALESCE(t.common_name_{g.locale}, t.scientific_name) as species_name
                FROM detections d
                JOIN visits v ON d.visit_id = v.id
                JOIN inaturalist_taxa t ON COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) = t.taxon_id
                WHERE d.id = ?
                    AND v.deleted_at IS NULL
            """,
                (detection_id,),
            ).fetchone()
        else:
            # Get next pending annotation
            current = conn.execute(f"""
                SELECT d.id, d.crop_path, d.bbox_x1, d.bbox_y1, d.bbox_x2, d.bbox_y2,
                       d.face_bbox_x1, d.face_bbox_y1, d.face_bbox_x2, d.face_bbox_y2,
                       d.annotation_source, d.detection_confidence, d.frame_timestamp,
                       t.scientific_name,
                       COALESCE(t.common_name_{g.locale}, t.scientific_name) as species_name
                FROM detections d
                JOIN visits v ON d.visit_id = v.id
                JOIN inaturalist_taxa t ON COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) = t.taxon_id
                WHERE d.annotation_source = 'machine'
                    AND v.deleted_at IS NULL
                ORDER BY d.id ASC
                LIMIT 1
            """).fetchone()

        # Get statistics
        stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN annotation_source IN ('human_confirmed', 'human_corrected', 'no_face')
                      THEN 1 END) as reviewed,
                COUNT(CASE WHEN annotation_source = 'machine' THEN 1 END) as pending
            FROM detections
            WHERE annotation_source IS NOT NULL
        """).fetchone()

    return render_template(
        "labeling.html",
        current_detection=current,
        stats=stats,
        current_index=stats["reviewed"] if stats else 0,
        return_url=return_url,
    )


@app.route("/api/labeling/<int:detection_id>/confirm", methods=["POST"])
def labeling_confirm(detection_id):
    """Confirm machine annotation as correct."""
    with db.get_connection() as conn:
        conn.execute(
            """
            UPDATE detections
            SET annotation_source = 'human_confirmed',
                reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (detection_id,),
        )
        conn.commit()
    return jsonify({"success": True})


@app.route("/api/labeling/<int:detection_id>/update", methods=["POST"])
def labeling_update(detection_id):
    """Update face bbox with human corrections."""
    data = request.json
    with db.get_connection() as conn:
        conn.execute(
            """
            UPDATE detections
            SET face_bbox_x1 = ?,
                face_bbox_y1 = ?,
                face_bbox_x2 = ?,
                face_bbox_y2 = ?,
                annotation_source = 'human_corrected',
                reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (data["x1"], data["y1"], data["x2"], data["y2"], detection_id),
        )
        conn.commit()
    return jsonify({"success": True})


@app.route("/api/labeling/<int:detection_id>/no-face", methods=["POST"])
def labeling_no_face(detection_id):
    """Mark detection as having no visible face."""
    with db.get_connection() as conn:
        conn.execute(
            """
            UPDATE detections
            SET annotation_source = 'no_face',
                reviewed_at = CURRENT_TIMESTAMP,
                face_bbox_x1 = NULL,
                face_bbox_y1 = NULL,
                face_bbox_x2 = NULL,
                face_bbox_y2 = NULL
            WHERE id = ?
        """,
            (detection_id,),
        )
        conn.commit()
    return jsonify({"success": True})


@app.route("/labeling/stats")
def labeling_stats():
    """Statistics dashboard for labeling progress."""
    with db.get_connection() as conn:
        # Overall stats
        stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN annotation_source IN ('human_confirmed', 'human_corrected', 'no_face')
                      THEN 1 END) as reviewed,
                COUNT(CASE WHEN annotation_source = 'human_confirmed'
                      THEN 1 END) as confirmed,
                COUNT(CASE WHEN annotation_source = 'human_corrected'
                      THEN 1 END) as corrected,
                COUNT(CASE WHEN annotation_source = 'machine'
                      THEN 1 END) as pending,
                COUNT(CASE WHEN annotation_source IS NULL
                      THEN 1 END) as not_annotated
            FROM detections
        """).fetchone()

        # Calculate confirmation rate
        reviewed_total = stats["confirmed"] + stats["corrected"]
        confirmation_rate = (
            stats["confirmed"] / reviewed_total if reviewed_total > 0 else 0
        )
        stats = dict(stats)
        stats["confirmation_rate"] = confirmation_rate

        # Per-species breakdown
        species_stats = conn.execute(f"""
            SELECT
                t.taxon_id as species_id,
                COALESCE(t.common_name_{g.locale}, t.scientific_name) as species_name,
                COUNT(*) as total,
                COUNT(CASE WHEN d.annotation_source IN ('human_confirmed', 'human_corrected', 'no_face')
                      THEN 1 END) as reviewed,
                COUNT(CASE WHEN d.annotation_source = 'machine'
                      THEN 1 END) as pending,
                COUNT(CASE WHEN d.annotation_source = 'human_confirmed'
                      THEN 1 END) as confirmed,
                COUNT(CASE WHEN d.annotation_source = 'human_corrected'
                      THEN 1 END) as corrected
            FROM detections d
            JOIN visits v ON d.visit_id = v.id
            JOIN inaturalist_taxa t ON COALESCE(v.override_taxon_id, v.inaturalist_taxon_id) = t.taxon_id
            WHERE d.annotation_source IS NOT NULL
                AND v.deleted_at IS NULL
            GROUP BY t.taxon_id, t.scientific_name, species_name
            ORDER BY total DESC
        """).fetchall()

        # Calculate confirmation rate per species
        species_stats_list = []
        for species in species_stats:
            species_dict = dict(species)
            reviewed = species["confirmed"] + species["corrected"]
            species_dict["confirmation_rate"] = (
                species["confirmed"] / reviewed if reviewed > 0 else 0
            )
            species_stats_list.append(species_dict)

    return render_template(
        "labeling_stats.html", stats=stats, species_stats=species_stats_list
    )


@app.route("/set-language")
def set_language():
    """Set the user's language preference."""
    lang = request.args.get("lang", DEFAULT_LANGUAGE)
    next_url = request.args.get("next", "/")

    # Validate language
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE

    # Create response with redirect
    response = redirect(next_url)

    # Set language cookie (1 year expiry)
    response.set_cookie("lang", lang, max_age=31536000)

    return response


def main():
    """Main entry point for the application."""
    from .scheduler import start_scheduler

    logger.info("starting_birdhomie_app")

    # Initialize database
    db.init_database()

    # Start background scheduler
    scheduler = start_scheduler(config)
    logger.info("background_scheduler_started")

    # Start the Flask app
    try:
        app.run(host="0.0.0.0", port=config.port, debug=config.flask_debug)
    finally:
        # Ensure scheduler shuts down cleanly
        if scheduler.running:
            scheduler.shutdown(wait=True)
            logger.info("background_scheduler_stopped")


if __name__ == "__main__":
    main()
