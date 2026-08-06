"""Put the repository root on `sys.path` so these tests import what the shell entry point does.

`scripts/can_node_watch.sh` runs the tool as `python3 -m scripts.can_node_watch` from the
repository root, and the tool resolves `backend`, `ops` and `contracts` from there. Collected by
path, pytest puts this directory on `sys.path` instead, which resolves none of them.

These tests live under `scripts/` rather than `tests/` because `scripts/**` is the only ownership
glob WP-ENV-03 declares (`06` §3.3), and CI-02b refuses a file no glob claims.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
