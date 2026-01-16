"""Global model cache for efficient model reuse across requests.

This module provides singleton instances of ML models that persist
across requests within a worker process, avoiding expensive reloading.
"""

import logging
from typing import Optional
from .detector import BirdDetector
from .classifier import BirdSpeciesClassifier
from .config import Config

logger = logging.getLogger(__name__)

# Global model instances (one per worker process)
_detector_instance: Optional[BirdDetector] = None
_classifier_instance: Optional[BirdSpeciesClassifier] = None


def get_detector(config: Config = None) -> BirdDetector:
    """Get or create the global detector instance.

    Args:
        config: Optional config for initial creation

    Returns:
        Cached BirdDetector instance
    """
    global _detector_instance

    if _detector_instance is None:
        logger.info("initializing_cached_detector")
        if config is None:
            config = Config.from_env()

        _detector_instance = BirdDetector(
            confidence_threshold=config.min_detection_confidence
        )
        # Eagerly load the model
        _detector_instance.load_model()
        logger.info("cached_detector_ready")

    return _detector_instance


def get_classifier() -> BirdSpeciesClassifier:
    """Get or create the global classifier instance.

    Returns:
        Cached BirdSpeciesClassifier instance
    """
    global _classifier_instance

    if _classifier_instance is None:
        logger.info("initializing_cached_classifier")
        _classifier_instance = BirdSpeciesClassifier()
        logger.info("cached_classifier_ready")

    return _classifier_instance


def preload_models(config: Config):
    """Preload all models into cache.

    This should be called during worker initialization to avoid
    lazy loading during the first request.

    Args:
        config: Application configuration
    """
    logger.info("preloading_models_into_cache")
    get_detector(config)
    get_classifier()
    logger.info("models_preloaded_successfully")


def clear_cache():
    """Clear the model cache (mainly for testing)."""
    global _detector_instance, _classifier_instance
    _detector_instance = None
    _classifier_instance = None
    logger.info("model_cache_cleared")
