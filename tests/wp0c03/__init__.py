"""WP-0C-03 acceptance suite — MJCF v2 asset audit and J7 motor-class fix.

Shared paths to the vendored assets, resolved from the ``sim.mjcf`` package so the
suite is independent of the working directory.
"""

from __future__ import annotations

from pathlib import Path

import sim.mjcf

MJCF_DIR = Path(sim.mjcf.__file__).resolve().parent
V2_DIR = MJCF_DIR / "v2"
BIMANUAL_XML = V2_DIR / "openarm_bimanual.xml"
CELL_XML = V2_DIR / "cell.xml"
CELL_REPARENTED_XML = V2_DIR / "cell_head_reparented.xml"
AUDIT_MD = MJCF_DIR / "AUDIT.md"

REPO_ROOT = MJCF_DIR.parents[1]
GATE_INDEX = REPO_ROOT / "registry" / "build" / "gate_index.json"

__all__ = [
    "AUDIT_MD",
    "BIMANUAL_XML",
    "CELL_REPARENTED_XML",
    "CELL_XML",
    "GATE_INDEX",
    "MJCF_DIR",
    "REPO_ROOT",
    "V2_DIR",
]
