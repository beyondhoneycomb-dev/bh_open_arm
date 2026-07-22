"""WP-3B-14 DEFERRED — real KER USB I/O, skipped-with-reason plus a re-verify hook.

A real KER read needs `pyusb` and `openarm_ker` and the physical ESP32-S3 device, none
of which exist on the dev desktop. So the real path is deferred: the USB reader raises
rather than fabricating a frame, and the re-verification hook returns a DEFERRED verdict
naming the absent dependency (never a fabricated pass — the one rule). When a real KER
is attached, `reverify_no_ik_and_zero_can` re-runs the no-IK / zero-CAN invariants on
real frames; that branch is exercised only under `real_device_available()`.
"""

from __future__ import annotations

import pytest

from backend.teleop.ker import (
    KerDeviceUnavailableError,
    OpenArmKER,
    OpenArmKERConfig,
    UsbKerDevice,
    real_device_available,
    reverify_no_ik_and_zero_can,
)
from backend.teleop.ker.reverify import STATUS_DEFERRED, STATUS_RUNS
from contracts.teleop import KER_USB_PID, KER_USB_VID


def test_real_device_absent_on_this_host() -> None:
    """The dev desktop has neither optional dep, so a real read cannot be attempted."""
    assert real_device_available() is False


def test_real_usb_reader_fails_loud_rather_than_fabricating() -> None:
    """Connecting the real USB reader without pyusb raises — it never returns fake data."""
    device = UsbKerDevice(KER_USB_VID, KER_USB_PID)
    with pytest.raises(KerDeviceUnavailableError):
        device.connect()
    assert not device.is_connected


def test_teleoperator_connect_propagates_the_unavailable_error() -> None:
    """The default plugin uses the real reader, so connect() fails loud without hardware."""
    teleop = OpenArmKER(OpenArmKERConfig())
    with pytest.raises(KerDeviceUnavailableError):
        teleop.connect()
    assert not teleop.is_connected


def test_reverify_defers_with_a_reason_when_hardware_is_absent() -> None:
    """The re-verify hook returns DEFERRED and names the missing dependency."""
    result = reverify_no_ik_and_zero_can()
    assert result.status == STATUS_DEFERRED
    assert result.frames_checked == 0
    assert "not installed" in result.reason


@pytest.mark.skipif(not real_device_available(), reason="no pyusb / openarm_ker / KER device")
def test_reverify_runs_on_real_hardware() -> None:
    """With a real KER present, the hook reads frames and confirms no IK / zero CAN."""
    result = reverify_no_ik_and_zero_can(frames=4)
    assert result.status == STATUS_RUNS
    assert result.frames_checked == 4
