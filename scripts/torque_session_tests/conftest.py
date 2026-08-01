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

from backend.actuation.config import RID9_NO_SEND_MARGIN_SEC, TICK_INTERVAL_SEC  # noqa: E402
from backend.preflight import PreflightReport  # noqa: E402
from backend.torque_bringup import (  # noqa: E402
    GatePass,
    GatewayBypassPrecondition,
    TorqueOnManifest,
    ZeroResidualPrecondition,
)
from backend.torque_bringup.constants import PG_RID_001, PG_SAFE_001  # noqa: E402
from tests.wp105.conftest import passing_check_results  # noqa: E402

# Evidence hashes for the two gate verdicts the engage is authorized against. Any non-empty
# string satisfies `is_pass_with_hash`; what these stand for is that the hash was declared
# somewhere other than in the code that reads it.
SAFE_HASH = "sha256:pg-safe-001-pass"
RID_HASH = "sha256:pg-rid-001-pass"


@pytest.fixture
def passing_preflight() -> PreflightReport:
    """A preflight report with all five torque-ON preconditions passed."""
    return PreflightReport(results=passing_check_results())


@pytest.fixture
def passing_manifest() -> TorqueOnManifest:
    """A startup manifest with all four torque-ON gate preconditions cleared."""
    return TorqueOnManifest(
        safe_gate=GatePass(gate_id=PG_SAFE_001, status="PASS", artifact_hash=SAFE_HASH),
        rid_gate=GatePass(gate_id=PG_RID_001, status="PASS", artifact_hash=RID_HASH),
        zero_residual=ZeroResidualPrecondition(within_tolerance=True),
        gateway_bypass=GatewayBypassPrecondition(bypass_count=0),
        rid9_send_period_sec=TICK_INTERVAL_SEC,
        rid9_no_send_margin_sec=RID9_NO_SEND_MARGIN_SEC,
    )


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
