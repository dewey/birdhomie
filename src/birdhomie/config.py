"""Configuration module with environment variable validation."""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """Application configuration with validation."""

    # Flask
    flask_debug: bool
    secret_key: str

    # UniFi Protect
    ufp_address: str
    ufp_username: str
    ufp_password: str
    ufp_camera_id: str
    ufp_detection_types: str
    ufp_ssl_verify: bool

    # Task intervals
    ufp_download_interval_minutes: int
    processor_interval_minutes: int

    # Detection thresholds
    min_species_confidence: float
    min_detection_confidence: float

    # Video processing
    frame_skip: int

    # Data retention
    file_retention_days: int

    # Face annotation
    face_annotation_batch_size: int

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment with validation."""

        # Required fields
        required = {
            "UFP_ADDRESS": os.getenv("UFP_ADDRESS"),
            "UFP_USERNAME": os.getenv("UFP_USERNAME"),
            "UFP_PASSWORD": os.getenv("UFP_PASSWORD"),
            "UFP_CAMERA_ID": os.getenv("UFP_CAMERA_ID"),
        }

        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        # Validate thresholds
        min_species = float(os.getenv("MIN_SPECIES_CONFIDENCE", "0.85"))
        if not 0 <= min_species <= 1:
            raise ValueError("MIN_SPECIES_CONFIDENCE must be between 0 and 1")

        min_detection = float(os.getenv("MIN_DETECTION_CONFIDENCE", "0.80"))
        if not 0 <= min_detection <= 1:
            raise ValueError("MIN_DETECTION_CONFIDENCE must be between 0 and 1")

        return cls(
            flask_debug=os.getenv("FLASK_DEBUG", "0") == "1",
            secret_key=os.getenv("SECRET_KEY", "dev-secret-key"),
            ufp_address=required["UFP_ADDRESS"],
            ufp_username=required["UFP_USERNAME"],
            ufp_password=required["UFP_PASSWORD"],
            ufp_camera_id=required["UFP_CAMERA_ID"],
            ufp_detection_types=os.getenv("UFP_DETECTION_TYPES", "motion"),
            ufp_ssl_verify=os.getenv("UFP_SSL_VERIFY", "false").lower() == "true",
            ufp_download_interval_minutes=int(os.getenv("UFP_DOWNLOAD_INTERVAL_MINUTES", "60")),
            processor_interval_minutes=int(os.getenv("PROCESSOR_INTERVAL_MINUTES", "5")),
            min_species_confidence=min_species,
            min_detection_confidence=min_detection,
            frame_skip=int(os.getenv("FRAME_SKIP", "5")),
            file_retention_days=int(os.getenv("FILE_RETENTION_DAYS", "30")),
            face_annotation_batch_size=int(os.getenv("FACE_ANNOTATION_BATCH_SIZE", "100")),
        )
