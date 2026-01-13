"""Shared pytest fixtures for birdhomie tests."""

import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from birdhomie.app import app
from birdhomie import database as db
from birdhomie.constants import DATA_DIR


@pytest.fixture
def client():
    """Create a test client with a temporary database."""
    # Create a temporary directory for test data
    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy the real database for integration tests
        test_db_path = Path(tmpdir) / "birdhomie.db"
        real_db_path = DATA_DIR / "birdhomie.db"

        if real_db_path.exists():
            shutil.copy(real_db_path, test_db_path)

        # Configure app for testing
        app.config.update({
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
        })

        # Patch database path for tests
        original_get_db_path = db.get_db_path
        db.get_db_path = lambda: test_db_path

        with app.test_client() as test_client:
            with app.app_context():
                yield test_client

        # Restore original
        db.get_db_path = original_get_db_path


@pytest.fixture
def client_empty_db():
    """Create a test client with a fresh empty database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db_path = Path(tmpdir) / "birdhomie.db"

        app.config.update({
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
        })

        original_get_db_path = db.get_db_path
        db.get_db_path = lambda: test_db_path

        # Initialize fresh database
        db.init_database()

        with app.test_client() as test_client:
            with app.app_context():
                yield test_client

        db.get_db_path = original_get_db_path
