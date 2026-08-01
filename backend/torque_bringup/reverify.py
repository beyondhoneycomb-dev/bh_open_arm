"""Real-fixture re-verification hook for the deferred torque-ON acceptances (`02a` §4.1).

Most of WP-1-05 runs on this host: the guarded-torque-ON ordering, the fitted-motor set, the
lease-expiry-forces-a-hold logic, the SAFE_HOLD-is-not-torque-0 check, and the manifest
PG-SAFE-001-hash gate. What does not run here is every acceptance that needs the arm powered
— the actual 0xFC engage on real motors, the present-pose hold under real gravity, the
power-cycle zero re-verify, and the hard-E-Stop drop. Those are deferred: skipped with a
reason, never asserted green, never dropped.

This is the hook the deferral is required to ship. The moment a directory of real captures is
supplied via `OPENARM_TORQUE_BRINGUP_REAL_FIXTURE`, `reverify_from_fixture` re-runs the
judgments this WP owns against the real numbers: the fitted-motor width check against the
fitted profile, and `build_present_pose_hold` with `assert_safe_hold` over the real engage
frame.

Two facts travel differently. The zero-residual tolerance verdict is WP-1-02's own run and the
E-Stop drop is a physical observation; neither is re-derivable from a capture, so both are
transcribed rather than recomputed. Absence is carried as the un-verified side of each — a
capture that never ran the stop reports the bus alive and no drop, which fails ⑨⑩ instead of
satisfying it by silence.

The release-to-CAN-stop latency is not among them. This WP produces no such measurement; the
clock constraint that puts it out of reach is stated in `stop_latency`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.endeffector import default_profile
from backend.torque_bringup.constants import FIXTURE_ENV_VAR
from backend.torque_bringup.hold import assert_safe_hold
from backend.torque_bringup.sequence import (
    FittedMotorMismatchError,
    assert_pose_covers_fitted_motors,
    build_present_pose_hold,
)
from contracts.units import Rad


@dataclass(frozen=True)
class RealVerification:
    """The verdicts a real capture produced, one per host file.

    Attributes:
        host_id: The control host the capture came from (`05` NFR-TEL-004).
        engaged_send_ids: The motor ids the real engage addressed. Always the fitted set —
            a capture naming any other id is refused, never carried in this field.
        engage_displacement_rad: Per-joint commanded displacement of the real engage; a
            guarded engage holds the present pose, so every entry is 0.0.
        zero_residual_within_tolerance: Whether the power-cycle zero residual held (shared
            with WP-1-02 acceptance ⑦).
        estop_can_alive: Whether CAN still answered after the hard E-Stop. An E-Stop cuts
            motor power, so the bus dies with it (`16` M-2). A capture that records no
            E-Stop observation reports True here, so silence cannot read as a pass.
        estop_drop_occurred: Whether the brakeless load fell when torque was lost (`12`
            NFR-SAF-009). A capture that records no E-Stop observation reports False.
    """

    host_id: str
    engaged_send_ids: tuple[int, ...]
    engage_displacement_rad: tuple[float, ...]
    zero_residual_within_tolerance: bool
    estop_can_alive: bool
    estop_drop_occurred: bool


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def assert_capture_addressed_fitted_motors(
    send_ids: tuple[int, ...], fitted_send_ids: tuple[int, ...]
) -> None:
    """Refuse a capture whose engage addressed anything other than the fitted motor set.

    The capture's own id list is not the authority on what the arm carries. A bus that
    polled an absent motor records that id and an angle for it, and the record is
    internally consistent — self-comparison admits it. The fitted profile is the only
    external truth, so the comparison is against that.

    Args:
        send_ids: The ids the captured engage addressed.
        fitted_send_ids: The ids the fitted tool declares.

    Raises:
        FittedMotorMismatchError: On any id set other than the fitted one.
    """
    if send_ids != fitted_send_ids:
        addressed = ", ".join(f"{send_id:#04x}" for send_id in send_ids)
        fitted = ", ".join(f"{send_id:#04x}" for send_id in fitted_send_ids)
        raise FittedMotorMismatchError(
            f"the capture's engage addressed ({addressed}) but the fitted tool carries "
            f"({fitted}); nobody answers on an id outside the fitted set, and the unanswered "
            "frames walk the controller to ERROR-PASSIVE and degrade the joints that are "
            "present, so the capture is refused rather than re-verified"
        )


def _verify_engage(capture: dict[str, Any]) -> tuple[tuple[int, ...], tuple[float, ...]]:
    """Rebuild and check the real present-pose hold engage.

    Args:
        capture: One parsed capture record.

    Returns:
        (tuple[tuple[int, ...], tuple[float, ...]]) The ids the engage addressed, and the
        per-joint commanded displacement.

    Raises:
        FittedMotorMismatchError: If the captured engage addressed an id the fitted tool
            does not carry, or the captured pose width is not the fitted motor count.
        SafeHoldViolationError: If the rebuilt hold frame is a torque-0 command.
    """
    engage = capture["engage"]
    send_ids = tuple(int(send_id) for send_id in engage["send_ids"])
    present = tuple(Rad(float(angle)) for angle in engage["present_pose_rad"])
    fitted_send_ids = default_profile().motor_send_ids
    assert_capture_addressed_fitted_motors(send_ids, fitted_send_ids)
    assert_pose_covers_fitted_motors(present, fitted_send_ids)
    hold_batch = build_present_pose_hold(present)
    assert_safe_hold(hold_batch)
    displacement = tuple(
        command.q.value - angle.value for command, angle in zip(hold_batch, present, strict=True)
    )
    return send_ids, displacement


def _verify_one(capture: dict[str, Any]) -> RealVerification:
    """Re-run every judgment over one real capture record.

    Args:
        capture: One parsed capture record.

    Returns:
        (RealVerification) The verdicts derived from the real numbers.
    """
    residual = capture.get("zero_residual", {})
    estop = capture.get("estop", {})
    send_ids, displacement = _verify_engage(capture)
    return RealVerification(
        host_id=str(capture.get("host_id", "unknown")),
        engaged_send_ids=send_ids,
        engage_displacement_rad=displacement,
        zero_residual_within_tolerance=bool(residual.get("within_tolerance", False)),
        # Absent E-Stop observations default to the un-verified side of each fact, so a
        # capture that never ran the stop cannot satisfy the deferred acceptance.
        estop_can_alive=bool(estop.get("can_alive", True)),
        estop_drop_occurred=bool(estop.get("drop_occurred", False)),
    )


def reverify_from_fixture(fixture_dir: Path) -> list[RealVerification]:
    """Re-run the WP-1-05 judgments against real captured measurements.

    Loads every `*.json` capture in the directory and runs the identical fitted-motor,
    guarded-engage and zero-residual judgments the offline tests exercise, now pointed at
    real numbers. This is the re-verification the deferred hardware acceptances require.

    Args:
        fixture_dir: Directory of captured measurement JSON files, one per host.

    Returns:
        (list[RealVerification]) One verification per capture file, ordered by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json torque-bringup capture in {fixture_dir}")
    return [_verify_one(json.loads(path.read_text(encoding="utf-8"))) for path in capture_files]
