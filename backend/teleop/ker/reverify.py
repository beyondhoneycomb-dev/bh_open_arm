"""Real-KER re-verification hook (WP-3B-14, plan 02a §4.1).

The no-IK and zero-CAN invariants are proven offline against a `MockKerDevice`, but a
real KER USB read can only be verified on hardware. This module is the hook that
re-runs the same invariants against a real device when one is present, and otherwise
reports a DEFERRED verdict with the reason — never a fabricated pass (the one rule:
never fake a real read).

The invariant it re-checks on hardware is exactly the offline one: `get_action()` maps
the leader's joint angles onto `.pos` degrees unchanged (no IK), with `.vel`/`.torque`
honest zeros, and the package carries no CAN symbol.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.teleop.ker.device import (
    KerReading,
    UsbKerDevice,
    module_available,
)
from backend.teleop.ker.keyset import position_channel_names
from backend.teleop.ker.staticcheck import RULE_CAN_SYMBOL, check_package
from contracts.teleop import (
    KER_USB_PID,
    KER_USB_VID,
    POSITION_SUFFIX,
    verify_non_position_dims_zero,
)

_PYUSB_MODULE = "usb.core"
_OPENARM_KER_MODULE = "openarm_ker.ker_stream"

STATUS_RUNS = "RUNS"
STATUS_DEFERRED = "DEFERRED"

# The package this hook re-verifies, resolved so the CAN scan runs from any cwd.
_KER_PACKAGE_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ReverifyResult:
    """The verdict of a re-verification attempt.

    Attributes:
        status: `RUNS` when a real device was read and checked, `DEFERRED` when the
            device or its deps were absent.
        reason: Why the attempt deferred, or a summary of what ran.
        frames_checked: How many real frames were verified (0 when deferred).
    """

    status: str
    reason: str
    frames_checked: int


def pyusb_available() -> bool:
    """Whether `pyusb` is installed."""
    return module_available(_PYUSB_MODULE)


def openarm_ker_available() -> bool:
    """Whether the upstream `openarm_ker` stream is installed."""
    return module_available(_OPENARM_KER_MODULE)


def real_device_available() -> bool:
    """Whether both optional deps for a real KER read are present.

    Returns:
        (bool) True only when a real USB read could be attempted. The dev desktop
        returns False, which routes every re-verification to a DEFERRED verdict.
    """
    return pyusb_available() and openarm_ker_available()


def _absent_dependency_reason() -> str:
    """Name the missing optional dependency for a DEFERRED verdict."""
    missing = [
        name
        for name, present in (
            (_PYUSB_MODULE, pyusb_available()),
            (_OPENARM_KER_MODULE, openarm_ker_available()),
        )
        if not present
    ]
    return f"real KER read deferred: {', '.join(missing)} not installed"


def verify_reading_is_ik_free(
    reading: KerReading, action: dict[str, float], bimanual: bool
) -> None:
    """Assert one action is the leader's joint angles with no IK and honest zeros.

    Args:
        reading: The KER frame the action was built from.
        action: The `get_action()` output for that frame.
        bimanual: Whether the keyset is bimanual.

    Raises:
        AssertionError: If any `.pos` value differs from the read joint angle (an IK
            solve or transform would change it), or a `.vel`/`.torque` value is nonzero.
    """
    positions = position_channel_names(bimanual)
    for name, angle in zip(positions, reading.joint_angles_deg, strict=True):
        if action[name] != angle:
            raise AssertionError(
                f"{name} = {action[name]} but the leader read {angle}; an IK solve or "
                "transform changed the joint angle (FR-TEL-064)"
            )
    verify_non_position_dims_zero(action)
    if any(not key.endswith(POSITION_SUFFIX) and value != 0.0 for key, value in action.items()):
        raise AssertionError("a non-position channel is nonzero (FR-TEL-064)")


def reverify_no_ik_and_zero_can(frames: int = 8, bimanual: bool = True) -> ReverifyResult:
    """Re-run the no-IK / zero-CAN invariants against a real KER, or defer with reason.

    Args:
        frames: How many real frames to read and check when a device is present.
        bimanual: Whether the KER is bimanual.

    Returns:
        (ReverifyResult) A `RUNS` verdict with the frame count when a real device was
        read, or a `DEFERRED` verdict naming the absent dependency. A real read is never
        fabricated: absent hardware always defers.
    """
    can_findings = [v for v in check_package(_KER_PACKAGE_ROOT) if v.rule == RULE_CAN_SYMBOL]
    if can_findings:
        return ReverifyResult(
            status=STATUS_RUNS,
            reason=f"static CAN scan found {len(can_findings)} symbol(s) — zero-CAN violated",
            frames_checked=0,
        )
    if not real_device_available():
        return ReverifyResult(
            status=STATUS_DEFERRED, reason=_absent_dependency_reason(), frames_checked=0
        )

    from backend.teleop.ker.keyset import ker_action

    device = UsbKerDevice(KER_USB_VID, KER_USB_PID)
    device.connect()
    checked = 0
    try:
        for _ in range(frames):
            reading = device.read()
            action = ker_action(reading.joint_angles_deg, bimanual, use_velocity_and_torque=True)
            verify_reading_is_ik_free(reading, action, bimanual)
            checked += 1
    finally:
        device.disconnect()
    return ReverifyResult(
        status=STATUS_RUNS,
        reason=f"read {checked} real KER frame(s): joint angles pass through, no CAN symbol",
        frames_checked=checked,
    )
