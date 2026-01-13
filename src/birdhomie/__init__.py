"""Birdhomie - Bird detection and classification system for UniFi Protect."""

import os
import warnings
from pathlib import Path

__version__ = "0.1.0"

# Suppress NNPACK warnings on hardware that doesn't support it.
# PyTorch automatically falls back to other backends when NNPACK isn't available.
# The actual availability is logged once at startup via configure_pytorch().
warnings.filterwarnings("ignore", message=".*NNPACK.*")

# Configure model cache directories to use data/models
# This must be set before importing torch, transformers, or open_clip
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_MODELS_DIR = _PROJECT_ROOT / "data" / "models"

# HuggingFace Hub cache (for BioCLIP and other HF models)
os.environ.setdefault("HF_HOME", str(_MODELS_DIR / "huggingface"))
os.environ.setdefault(
    "TRANSFORMERS_CACHE", str(_MODELS_DIR / "huggingface" / "transformers")
)
os.environ.setdefault("HF_HUB_CACHE", str(_MODELS_DIR / "huggingface" / "hub"))

# PyTorch Hub cache (for other torch models)
os.environ.setdefault("TORCH_HOME", str(_MODELS_DIR / "torch"))


def configure_pytorch(logger=None, num_threads: int = 2) -> dict:
    """
    Configure PyTorch for optimal CPU inference.

    This function limits thread count to prevent CPU contention in containers.
    NNPACK warnings are suppressed globally at module load time.

    Args:
        logger: Optional logger instance. If None, prints to stdout.
        num_threads: Number of threads for PyTorch operations (default: 2)

    Returns:
        dict with configuration status:
        - num_threads: int
    """
    import torch

    # Limit threads to prevent over-subscription in containers
    torch.set_num_threads(num_threads)

    status = {"num_threads": num_threads}

    if logger:
        logger.info("pytorch_configured", extra=status)
    else:
        print(f"PyTorch configured: using {num_threads} threads")

    return status
