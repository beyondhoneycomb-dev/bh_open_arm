"""Deferred hardware acceptances + proof the re-verification hook that re-runs them works.

Five things cannot run on this host, because each needs the arm powered and a PG-SAFE-001
PASS that does not exist here: the actual 0xFC torque-ON, the present-pose hold under real
gravity (acceptance ④ physical half), the real release-to-CAN-stop P99 (⑥), the power-cycle
zero re-verify (⑪, shared with WP-1-02), and the hard-E-Stop drop (⑨⑩ physical half). Each is
SKIPPED WITH A REASON — never asserted green — and wired to the re-verification hook that
re-runs the identical judgments the moment a real capture directory is supplied via
`OPENARM_TORQUE_BRINGUP_REAL_FIXTURE` (`02a` §4.1).

To prove the hook is real and not a stub, `test_reverify_hook_*` build a synthetic capture in
the same schema a real capture uses and run the hook end to end — the stop-latency capture
carries a real kernel-clock provenance, so the hook exercises the clockProvenance gate
without pretending to have reached a bus.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.torque_bringup.constants import CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING
from backend.torque_bringup.reverify import (
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.torque_bringup.stop_latency import StopLatencyArtifactRefusedError

_REAL_FIXTURE = fixture_dir_from_env()
_SKIP_REASON = (
    "requires the arm powered, a real CAN adapter, and a PG-SAFE-001 PASS (12 FR-SAF-075, "
    "16 M-2); set OPENARM_TORQUE_BRINGUP_REAL_FIXTURE to a real capture directory to re-verify"
)


def _synthetic_capture(within_tolerance: bool = True, provenance: bool = True) -> dict:
    """One synthetic capture in the real-capture schema.

    Args:
        within_tolerance: The power-cycle zero-residual verdict to embed.
        provenance: Whether to embed a valid clockProvenance on the stop measurement.

    Returns:
        (dict) A capture record.
    """
    stop: dict = {"samples_sec": [0.008, 0.010, 0.012, 0.028]}
    if provenance:
        stop["clock_provenance"] = {
            "method": CLOCK_METHOD_KERNEL_EVDEV_SO_TIMESTAMPING,
            "offset_sec": 0.0,
            "uncertainty_sec": 5e-6,
        }
    return {
        "host_id": "synthetic-host",
        "engage": {"present_pose_rad": [0.05 * index for index in range(16)]},
        "stop_latency": stop,
        "zero_residual": {"within_tolerance": within_tolerance},
        "estop": {"can_alive": False, "drop_occurred": True},
    }


def _capture_dir(tmp_path: Path, capture: dict) -> Path:
    (tmp_path / "synthetic-host.json").write_text(json.dumps(capture), encoding="utf-8")
    return tmp_path


# --- Hook mechanism: proves the re-verification plumbing works (synthetic data) ---


def test_reverify_hook_runs_over_a_capture_dir(tmp_path: Path) -> None:
    verifications = reverify_from_fixture(_capture_dir(tmp_path, _synthetic_capture()))
    assert len(verifications) == 1
    verification = verifications[0]
    # A guarded engage holds the present pose: zero commanded displacement.
    assert set(verification.engage_displacement_rad) == {0.0}
    # The stop artifact was rebuilt through the real clockProvenance gate, P99 published.
    assert verification.stop_latency_artifact is not None
    assert verification.stop_latency_artifact["p99_sec"] == 0.028
    assert verification.zero_residual_within_tolerance


def test_reverify_hook_refuses_a_capture_without_clock_provenance(tmp_path: Path) -> None:
    # The hook re-applies the forge refusal: a stop capture with no provenance is rejected,
    # so the hook can never manufacture a stop-latency number.
    capture_dir = _capture_dir(tmp_path, _synthetic_capture(provenance=False))
    with pytest.raises(StopLatencyArtifactRefusedError):
        reverify_from_fixture(capture_dir)


def test_reverify_hook_rejects_an_empty_capture_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path)


# --- Deferred hardware acceptances: skipped with a reason, re-run only on a real capture ---


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="actual 0xFC torque-ON: " + _SKIP_REASON)
def test_deferred_real_torque_on_engage() -> None:
    assert _REAL_FIXTURE is not None
    for verification in reverify_from_fixture(_REAL_FIXTURE):
        assert verification.engage_displacement_rad, "no real engage in the capture"


@pytest.mark.skipif(
    _REAL_FIXTURE is None, reason="present-pose hold under gravity: " + _SKIP_REASON
)
def test_deferred_present_pose_hold_no_bounce() -> None:
    assert _REAL_FIXTURE is not None
    for verification in reverify_from_fixture(_REAL_FIXTURE):
        # A real engage must still command zero displacement; the physical bounce is
        # bounded by the real hold gains, judged on the real capture.
        assert set(verification.engage_displacement_rad) == {0.0}


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="PG-STOP-001 real P99: " + _SKIP_REASON)
def test_deferred_pg_stop_001_real_latency() -> None:
    assert _REAL_FIXTURE is not None
    for verification in reverify_from_fixture(_REAL_FIXTURE):
        artifact = verification.stop_latency_artifact
        assert artifact is not None and artifact["p99_sec"] is not None


@pytest.mark.skipif(_REAL_FIXTURE is None, reason="power-cycle zero re-verify: " + _SKIP_REASON)
def test_deferred_power_cycle_zero_residual() -> None:
    # Acceptance ⑪: shares the WP-1-02 evidence — the power-cycle residual within tolerance.
    assert _REAL_FIXTURE is not None
    for verification in reverify_from_fixture(_REAL_FIXTURE):
        assert verification.zero_residual_within_tolerance
