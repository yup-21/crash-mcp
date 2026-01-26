"""Pytest configuration and shared fixtures for crash-mcp tests."""
import sys
import os

# Add src to path for all tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import pytest
from pathlib import Path


# Paths to mock scripts
FIXTURES_DIR = Path(__file__).parent / "fixtures"
MOCK_CRASH_PATH = FIXTURES_DIR / "mock_crash.py"
MOCK_DRGN_PATH = FIXTURES_DIR / "mock_drgn.py"


@pytest.fixture
def mock_crash_path():
    """Return path to mock crash script."""
    os.chmod(MOCK_CRASH_PATH, 0o755)
    return str(MOCK_CRASH_PATH)


@pytest.fixture
def mock_drgn_path():
    """Return path to mock drgn script."""
    os.chmod(MOCK_DRGN_PATH, 0o755)
    return str(MOCK_DRGN_PATH)


@pytest.fixture
def temp_workdir(tmp_path):
    """Create a temporary working directory."""
    workdir = tmp_path / "crash_workdir"
    workdir.mkdir()
    return workdir
