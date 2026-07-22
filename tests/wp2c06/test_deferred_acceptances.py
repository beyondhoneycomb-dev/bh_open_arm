"""The deferred on-rig reaction time: skipped with a reason, re-run by the hook.

The real detection-confirm-to-CAN reaction-frame measurement cannot run on this host — it
needs a torque-ON rig and the kernel-clock instrumentation `03` §5.7.0 requires. So it is
SKIPPED WITH A REASON, never asserted green, and wired to the re-verification hook that
re-runs the identical bench the moment a real capture directory is supplied via
`OPENARM_REACTION_BENCH_REAL_FIXTURE` (`02a` §4.1).

To prove the hook is real and not a stub, `test_reverify_hook_*` build a capture in the same
schema a real capture uses and run the hook end to end — including that a capture naming the
candump forge as its clock is refused, so the hook can never manufacture a reaction time.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.reaction_bench import ReactionLatencyRefusedError, reverify_from_fixture
from backend.reaction_bench.bench import REAL_CAPTURE_BASIS
from backend.reaction_bench.reverify import fixture_dir_from_env
from backend.torque_bringup.constants import (
    CLOCK_METHOD_CANDUMP_HW_TIMESTAMP,
    CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING,
)

_REAL_FIXTURE = fixture_dir_from_env()
_SKIP_REASON = (
    "requires a torque-ON rig and kernel-clock instrumentation (03 §5.7.0: evdev kernel ts "
    "x SO_TIMESTAMPING, or an independent GPIO marker); set OPENARM_REACTION_BENCH_REAL_FIXTURE "
    "to a real capture directory to re-verify"
)


def _capture(method: str) -> dict[str, object]:
    """Build one capture record in the capture schema.

    Args:
        method: The clock-provenance method to declare.

    Returns:
        (dict) A capture with a small monotonic sample set and the given clock method.
    """
    samples = [
        {
            "detection_confirm_at": index * 0.001,
            "reaction_select_at": index * 0.001 + 0.002,
            "scheduler_write_at": index * 0.001 + 0.005,
            "can_first_byte_at": index * 0.001 + 0.009,
        }
        for index in range(10)
    ]
    return {
        "host_id": "synthetic-host",
        "clock_provenance": {"method": method, "offset_sec": 1e-6, "uncertainty_sec": 1e-7},
        "samples": samples,
    }


def _capture_dir(tmp_path: Path, method: str) -> Path:
    """Write one synthetic capture into a directory.

    Args:
        tmp_path: The pytest temp directory.
        method: The clock-provenance method to declare.

    Returns:
        (Path) The directory holding the capture file.
    """
    (tmp_path / "synthetic-host.json").write_text(json.dumps(_capture(method)), encoding="utf-8")
    return tmp_path


# --- Hook mechanism: proves the re-verification plumbing works (synthetic data) ---


def test_reverify_hook_runs_over_a_capture_dir(tmp_path: Path) -> None:
    directory = _capture_dir(tmp_path, CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING)
    artifacts = reverify_from_fixture(directory)
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact["basis"] == REAL_CAPTURE_BASIS
    assert artifact["no_disable_torque_precondition"]["passed"] is True
    assert artifact["reaction_time"]["sample_count"] == 10
    assert artifact["reaction_time"]["total"]["raw_samples"]


def test_reverify_hook_rejects_an_empty_capture_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path)


def test_reverify_hook_refuses_a_candump_forge_capture(tmp_path: Path) -> None:
    directory = _capture_dir(tmp_path, CLOCK_METHOD_CANDUMP_HW_TIMESTAMP)
    with pytest.raises(ReactionLatencyRefusedError):
        reverify_from_fixture(directory)


# --- Deferred on-rig acceptance: skipped with a reason, re-run only on a real capture ---


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="on-rig reaction time: " + _SKIP_REASON)
def test_deferred_on_rig_reaction_time() -> None:
    assert _REAL_FIXTURE is not None
    for artifact in reverify_from_fixture(_REAL_FIXTURE):
        assert artifact["reaction_time"]["sample_count"] > 0, "no real samples in the capture"
        assert artifact["reaction_time"]["total"]["raw_samples"]
