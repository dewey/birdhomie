# Birdhomie

Bird detection and classification system for UniFi Protect with web interface.

## Features

- Automatic bird detection using YOLOv8m
- Species classification using BioCLIP-2
- Face detection and annotation for bird portraits
- UniFi Protect integration for automatic video download
- Web interface for viewing detections and species
- Species information from iNaturalist and Wikipedia
- Visit tracking and photo galleries
- Manual labeling interface for reviewing face annotations
- Internationalization support (English, German)

## Prerequisites

- macOS 13+ or Linux
- Python 3.14+
- [uv](https://github.com/astral-sh/uv) for package management
- UniFi Protect NVR with a camera configured for smart detection
- (Optional) [direnv](https://direnv.net/) for automatic environment variable loading

## Setup

### 1. Install uv

If you don't have uv installed:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone and Install Dependencies

```bash
git clone <repository-url>
cd birdhomie
uv sync
```

### 3. Configure Environment Variables

Copy the example environment file and configure it:
```bash
cp .envrc.example .envrc
# Edit .envrc with your UniFi Protect credentials and settings
```

**Required variables:**
- `UFP_ADDRESS`: IP address of your UniFi Protect NVR
- `UFP_USERNAME`: Local user username (create a Local Access Only user)
- `UFP_PASSWORD`: Local user password
- `UFP_CAMERA_ID`: Camera ID to monitor (find in Protect web UI)

**Optional variables:**
- `FLASK_DEBUG`: Enable Flask debug mode (default: `0`)
- `SECRET_KEY`: Flask secret key (default: `dev-secret-key`)
- `UFP_DETECTION_TYPES`: Detection types to monitor (default: `motion`)
- `UFP_SSL_VERIFY`: Verify SSL certificates for UniFi Protect (default: `false`)
- `UFP_DOWNLOAD_INTERVAL_MINUTES`: Download interval in minutes (default: `30`)
- `PROCESSOR_INTERVAL_MINUTES`: Processing interval in minutes (default: `5`)
- `MIN_SPECIES_CONFIDENCE`: Minimum confidence for species ID (default: `0.85`)
- `MIN_DETECTION_CONFIDENCE`: Minimum confidence for bird detection (default: `0.80`)
- `FRAME_SKIP`: Process every N frames (default: `5`)
- `FILE_RETENTION_DAYS`: Days to retain processed files (default: `30`)
- `FACE_ANNOTATION_BATCH_SIZE`: Batch size for face annotation (default: `100`)

**Using direnv (recommended):**
If you have direnv installed, allow it to load the environment:
```bash
direnv allow
```

**Without direnv:**
Source the environment file manually before running commands:
```bash
source .envrc
```

### 4. Initialize Database

```bash
make init-db
```

### 5. Start the Application

**Development mode (recommended for testing):**
```bash
make dev
```

This will:
- Compile translations
- Start Flask with hot reloading
- Enable debug mode
- Run on http://127.0.0.1:5001

**Production mode:**
```bash
make run
```

## Development

### Running in Development Mode

The `make dev` command is the recommended way to run the app during development:
```bash
source .envrc  # If not using direnv
make dev
```

This automatically:
- Compiles translation files
- Starts the Flask development server with hot reload
- Enables debug mode with detailed error pages
- Watches for file changes and restarts automatically

### Available Make Commands

- `make dev` - Run with hot reloading (development mode)
- `make run` - Run in normal mode
- `make compile-translations` - Compile .po files to .mo files
- `make extract-translations` - Extract translatable strings
- `make update-translations` - Update translation catalogs
- `make init-db` - Initialize database
- `make migrate` - Run pending migrations
- `make process` - Run file processor manually
- `make clean` - Clean generated files
- `make help` - Show available commands

## Web Interface

Once running, access the web interface at http://127.0.0.1:5001

**Pages:**
- `/` - Dashboard with recent visits and species
- `/species` - List of all detected species
- `/species/<id>` - Species detail page with photos and visits
- `/visits/<id>` - Individual visit details with video player
- `/files` - List of all processed files
- `/tasks` - Background task status
- `/labeling` - Manual labeling interface for face annotations
- `/labeling/stats` - Labeling progress and statistics
- `/settings` - Application settings

## UniFi Protect Integration

### Setup

1. Create a **Local Access Only** user on your UniFi Protect NVR
2. Give the user "Full Management" permissions
3. Get your camera ID from the Protect web UI (Settings → Camera → Advanced)
4. Add credentials to `.envrc`

### Automatic Download

The application automatically downloads smart detection events from UniFi Protect every 30 minutes (configurable via `UFP_DOWNLOAD_INTERVAL_MINUTES`).

### Manual Trigger

Trigger downloads from the Tasks page in the web interface or via API:
```bash
curl http://127.0.0.1:5001/tasks/trigger/unifi_download
```

## Translations

The application supports multiple languages. Currently supported:
- English (en) - default
- German (de)

### Adding New Translations

1. Extract translatable strings:
```bash
make extract-translations
```

2. Update translation catalogs:
```bash
make update-translations
```

3. Edit translation files in `src/birdhomie/translations/<lang>/LC_MESSAGES/messages.po`

4. Compile translations:
```bash
make compile-translations
```

## Troubleshooting

### App Won't Start - Missing Environment Variables

If you see "Missing required environment variables", make sure you've:
1. Created the `.envrc` file from `.envrc.example`
2. Configured all required variables
3. Sourced the file (`source .envrc`) or allowed direnv (`direnv allow`)

### Port Already in Use

If port 5001 is already in use, you can change it in the Makefile or stop the conflicting process.

## Configuration Reference

See `.envrc.example` for all available configuration options and their descriptions.
