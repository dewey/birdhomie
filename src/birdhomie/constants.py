"""Centralized constants for the birdhomie application."""

from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
SPECIES_IMAGES_DIR = DATA_DIR / "species_images"
LOGS_DIR = DATA_DIR / "logs"
MODELS_DIR = DATA_DIR / "models"
DB_PATH = DATA_DIR / "birdhomie.db"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"

# YOLO
BIRD_CLASS_ID = 14
YOLO_MODEL_PATH = str(MODELS_DIR / "yolov8m.pt")

# BioCLIP
BIOCLIP_MODEL_NAME = "bioclip-2"

# Localization
DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = {"en": "English", "de": "Deutsch"}

# File types
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}
