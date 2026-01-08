"""Birdhomie - Bird detection and classification system for UniFi Protect."""

import os
from pathlib import Path

__version__ = "0.1.0"

# Configure model cache directories to use data/models
# This must be set before importing torch, transformers, or open_clip
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_MODELS_DIR = _PROJECT_ROOT / "data" / "models"

# HuggingFace Hub cache (for BioCLIP and other HF models)
os.environ.setdefault("HF_HOME", str(_MODELS_DIR / "huggingface"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(_MODELS_DIR / "huggingface" / "transformers"))
os.environ.setdefault("HF_HUB_CACHE", str(_MODELS_DIR / "huggingface" / "hub"))

# PyTorch Hub cache (for other torch models)
os.environ.setdefault("TORCH_HOME", str(_MODELS_DIR / "torch"))
