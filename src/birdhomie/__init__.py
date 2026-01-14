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

    This function:
    - Limits thread count to prevent CPU contention in containers
    - Optionally disables NNPACK backend via NNPACK_DISABLE env var
    - Sets inter-op parallelism for efficient CPU usage

    NNPACK warnings are suppressed globally at module load time.

    Environment variables:
        NNPACK_DISABLE: Set to "1" to disable NNPACK backend. Use this on CPUs
            without AVX2/FMA support (pre-2013 Intel, pre-2015 AMD) to prevent
            repeated initialization attempts that cause high CPU usage.

    Args:
        logger: Optional logger instance. If None, prints to stdout.
        num_threads: Number of threads for PyTorch operations (default: 2)

    Returns:
        dict with configuration status:
        - num_threads: int
        - interop_threads: int
        - nnpack_enabled: bool
    """
    import torch

    # Limit intra-op threads (within a single operation)
    torch.set_num_threads(num_threads)

    # Limit inter-op threads (parallel operations)
    torch.set_num_interop_threads(1)

    # Check if NNPACK should be disabled via environment variable
    # Useful for CPUs without AVX2/FMA (e.g., Intel pre-Haswell, AMD pre-Excavator)
    nnpack_disable = os.environ.get("NNPACK_DISABLE", "").lower() in (
        "1",
        "true",
        "yes",
    )
    nnpack_enabled = True

    if hasattr(torch.backends, "nnpack"):
        if nnpack_disable:
            torch.backends.nnpack.enabled = False
        nnpack_enabled = torch.backends.nnpack.enabled

    status = {
        "num_threads": num_threads,
        "interop_threads": 1,
        "nnpack_enabled": nnpack_enabled,
    }

    if logger:
        logger.info("pytorch_configured", extra=status)
    else:
        print(f"PyTorch configured: {num_threads} threads, nnpack={nnpack_enabled}")

    return status
