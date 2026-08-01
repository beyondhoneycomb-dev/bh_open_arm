"""Put the repository root on `sys.path` so these tests import what the shell entry point does.

`scripts/torque_session.sh` runs the runner as `python3 -m scripts.torque_session` from the
repository root, and the runner resolves `backend`, `ops`, `packages` and `contracts` from
there. Collected by path, pytest puts this directory on `sys.path` instead, which resolves
none of them.

These tests live under `scripts/` rather than `tests/` because `scripts/**` is the only
ownership glob WP-ENV-03 declares (`06` §3.3), and CI-02b refuses a file no glob claims.
`scripts/gates.sh` names both trees on its pytest line for the same reason.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def no_process_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn reaching `subprocess.run` into a failure, for tests where a refusal comes first.

    Without it, a privilege refusal that stopped firing does not fail its test — it escalates for
    real. `pkexec` and `su` read their password from the controlling terminal rather than from
    stdin, so the run hangs on an authentication prompt nobody is watching and the suite returns
    no verdict at all, which reads as neither green nor red.
    """

    def _executed(argv: list[str], **_kwargs: object) -> None:
        raise AssertionError(f"a refusal was expected before this ran: {argv}")

    monkeypatch.setattr(subprocess, "run", _executed)
