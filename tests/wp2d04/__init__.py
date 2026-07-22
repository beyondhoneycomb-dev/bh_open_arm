"""WP-2D-04 acceptance suite — Freedrive virtual-wall repulsion and detection switch.

Shared paths. The Freedrive band reuses the GMO residual, the comm-loss watchdog, the
temperature monitor, the soft limits, and the WP-2C-07 Cartesian walls; the GMO and sim
imports pull the optional robot stack (mujoco/openarm_control/LeRobot), so the modules that
need it ``importorskip`` those, matching the WP-2D-01 suite.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FREEDRIVE_PACKAGE_DIR = REPO_ROOT / "backend" / "freedrive_walls"

__all__ = ["FREEDRIVE_PACKAGE_DIR", "REPO_ROOT"]
