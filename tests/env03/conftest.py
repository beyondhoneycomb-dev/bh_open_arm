"""Put the `.github/` gate scripts on the import path for WP-ENV-03 tests.

The pre-merge gates live under `.github/` (WP-ENV-03's owned tree), which is not an
importable package location by default. Adding it here — before the test modules are
imported — lets them `import ownership_diff` / `gate_report` / `premerge_lint`
directly rather than through a path hack in every test file.
"""

from __future__ import annotations

import sys
from pathlib import Path

_GITHUB_DIR = Path(__file__).resolve().parents[2] / ".github"
if str(_GITHUB_DIR) not in sys.path:
    sys.path.insert(0, str(_GITHUB_DIR))
