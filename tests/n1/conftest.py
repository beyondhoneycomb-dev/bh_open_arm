"""Shared fixtures for the Wave -1 normalization ledger tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from registry.normalization.loader import LEDGER_PATH, load_ledger

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "registry" / "normalization" / "fixtures"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the repository root the corpus is resolved from."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def ledger() -> dict[str, Any]:
    """Load the real normalization ledger."""
    return load_ledger(LEDGER_PATH)
