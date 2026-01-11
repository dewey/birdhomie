#!/usr/bin/env python3
"""Test script to process a single file."""

import logging
from pathlib import Path
from src.birdhomie.config import Config
from src.birdhomie.processor import FileProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Load config
config = Config.from_env()

# Create processor
processor = FileProcessor(config)

# Process all files in input directory
input_dir = Path("data/input")
for file_path in input_dir.glob("*.mp4"):
    print(f"Processing {file_path}...")
    success = processor.process_file(file_path)
    print(f"Processing {file_path.name}: {'succeeded' if success else 'failed'}")
