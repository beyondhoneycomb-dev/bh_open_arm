"""WP-0C-07 acceptance suite — learning/eval statistics on a synthetic dataset.

Shared repository paths, resolved from this file so the suite is independent of
the working directory.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEARNING_DIR = REPO_ROOT / "backend" / "learning"

__all__ = [
    "LEARNING_DIR",
    "REPO_ROOT",
]
