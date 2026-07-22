"""WP-2D-09 acceptance suite — numeric Move-to (check first, execute only on pass).

Shared paths. The behavioural tests drive the reused Cartesian jog (WP-2D-01) and so
``importorskip`` the optional ``[robot]`` stack; the static tests (the no-second-IK scan
and the single-guarded-execution-site proof) read source with ``ast`` and need no such
import, so they run in the light lane too.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MOVETO_PACKAGE_DIR = REPO_ROOT / "backend" / "moveto"
GATE_MODULE = MOVETO_PACKAGE_DIR / "gate.py"

__all__ = ["GATE_MODULE", "MOVETO_PACKAGE_DIR", "REPO_ROOT"]
