"""Canonical-path fixture: dynamic import of the banned module via importlib.

Proves the scan sees the `importlib.import_module("openarm_driver")` route around
a static import statement (acceptance ③).
"""

from __future__ import annotations

import importlib


def load_driver() -> object:
    """Import the banned driver dynamically — still a canonical-path double bind."""
    return importlib.import_module("openarm_driver")
