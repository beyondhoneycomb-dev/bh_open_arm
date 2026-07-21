"""Shared fixture loaders for the WP-OPS-03 tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a manifest fixture from the WP-OPS-03 fixtures directory.

    Args:
        name: The fixture file name, e.g. `range_operators.yaml`.

    Returns:
        (dict[str, Any]) The parsed fixture mapping.
    """
    loaded: Any = yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def deterministic_probes() -> tuple[str, str]:
    """Return fixed (lerobot_sha, mujoco) values for offline-deterministic reporting."""
    return ("0" * 40, "3.10.0")
