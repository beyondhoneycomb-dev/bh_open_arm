"""Exposure and white balance: that the declaration is ordered by the device's rules, not ours.

Every case runs against `FakeCameraControls`, which answers a write the three ways the driver
does — a value clamped into an integer control's bounds and reported as success, an EACCES for a
control an automatic mode still holds inactive, and an EINVAL for a menu entry the device does
not offer. Only the first is silent, and it is the one the readback check exists to catch; the
other two are what a caller needs an error branch for. A fake that accepted every write would
let the whole comparison pass while verifying nothing, so the cases below are written to die if
the fake ever softens.

The bounds and power-up values the fake is built from were read off both wrist units and the
ZED-M with `VIDIOC_QUERYCTRL`. What still needs a camera is the declaration itself — 60 / 200 /
4000 K were measured on a sibling rig under its lighting, and `PG-CAM-001` re-measures them on
this bench.
"""

from __future__ import annotations

import errno

import pytest

from backend.camera.constants import (
    ARDUCAM_AUTO_EXPOSURE_AUTO_MODE,
    ARDUCAM_AUTO_EXPOSURE_MANUAL,
    ARDUCAM_AUTO_EXPOSURE_MENU_ENTRIES,
    ARDUCAM_EXPOSURE_TIME_ABSOLUTE,
    ARDUCAM_EXPOSURE_TIME_MAXIMUM,
    ARDUCAM_EXPOSURE_TIME_MINIMUM,
    ARDUCAM_GAIN,
    ARDUCAM_GAIN_MAXIMUM,
    ARDUCAM_GAIN_MINIMUM,
    ARDUCAM_PIXEL_FORMAT,
    ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF,
    ARDUCAM_WHITE_BALANCE_AUTOMATIC_ON,
    ARDUCAM_WHITE_BALANCE_TEMPERATURE_DEFAULT,
    ARDUCAM_WHITE_BALANCE_TEMPERATURE_K,
    CONTROL_AUTO_EXPOSURE,
    CONTROL_EXPOSURE_TIME_ABSOLUTE,
    CONTROL_GAIN,
    CONTROL_WHITE_BALANCE_AUTOMATIC,
    CONTROL_WHITE_BALANCE_TEMPERATURE,
)
from backend.camera.controls import (
    WRIST_CAMERA_CONTROLS,
    CameraControl,
    CameraControlError,
    assert_controls_locked,
    decode_fourcc,
    pixel_format_finding,
    plan_control_writes,
    verify_control_readback,
)
from backend.camera.fixtures import FakeCameraControls, arducam_control_set, zed_uvc_control_set

# The packed FOURCC words as a capture backend reports them: four ASCII bytes, low byte first.
YUYV_FOURCC = 0x56595559
MJPG_FOURCC = 0x47504A4D

CAMERA_LABEL = "wrist_right"

# A declaration written in the order a person would say it out loud, with each automatic switch
# after the control it guards — the order the device refuses.
BADLY_ORDERED_DECLARATION = (
    CameraControl(CONTROL_EXPOSURE_TIME_ABSOLUTE, ARDUCAM_EXPOSURE_TIME_ABSOLUTE),
    CameraControl(CONTROL_AUTO_EXPOSURE, ARDUCAM_AUTO_EXPOSURE_MANUAL),
    CameraControl(CONTROL_WHITE_BALANCE_TEMPERATURE, ARDUCAM_WHITE_BALANCE_TEMPERATURE_K),
    CameraControl(CONTROL_WHITE_BALANCE_AUTOMATIC, ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF),
)


def _apply(device: FakeCameraControls, controls: tuple[CameraControl, ...]) -> None:
    """Write the controls to the device in exactly the order given."""
    for control in controls:
        device.write(control.name, control.value)


def test_an_auto_switch_is_written_before_the_control_it_gates() -> None:
    """The declaration lists each switch last; the plan must not preserve that."""
    device = arducam_control_set()

    plan = plan_control_writes(BADLY_ORDERED_DECLARATION, device.read())

    names = [control.name for control in plan.ordered]
    assert names.index(CONTROL_AUTO_EXPOSURE) < names.index(CONTROL_EXPOSURE_TIME_ABSOLUTE)
    assert names.index(CONTROL_WHITE_BALANCE_AUTOMATIC) < names.index(
        CONTROL_WHITE_BALANCE_TEMPERATURE
    )


def test_both_spellings_of_an_auto_switch_are_recognised() -> None:
    """`auto_exposure` leads with the word and `white_balance_automatic` carries it inside."""
    device = arducam_control_set()

    plan = plan_control_writes(BADLY_ORDERED_DECLARATION, device.read())

    leading = [control.name for control in plan.ordered[:2]]
    assert sorted(leading) == sorted([CONTROL_AUTO_EXPOSURE, CONTROL_WHITE_BALANCE_AUTOMATIC])


def test_the_shipped_declaration_is_not_ordered_by_its_own_line_order() -> None:
    """Reversing the tuple must not change what gets written first."""
    device = arducam_control_set()

    forward = plan_control_writes(WRIST_CAMERA_CONTROLS, device.read())
    backwards = tuple(reversed(WRIST_CAMERA_CONTROLS))
    reversed_declaration = plan_control_writes(backwards, device.read())

    forward_switches = [c.name for c in forward.ordered[:2]]
    reversed_switches = [c.name for c in reversed_declaration.ordered[:2]]
    assert sorted(forward_switches) == sorted(reversed_switches)
    assert CONTROL_EXPOSURE_TIME_ABSOLUTE not in forward_switches
    assert CONTROL_EXPOSURE_TIME_ABSOLUTE not in reversed_switches


def test_a_write_made_while_its_auto_switch_is_on_is_refused_by_the_device() -> None:
    """Written in the bad order, the exposure write never lands — and it is not quiet about it.

    This is the branch a caller most needs to have somewhere to put: the failure arrives as an
    exception from the write, not as a wrong value the readback comparison later notices.
    """
    device = arducam_control_set()

    with pytest.raises(PermissionError) as refusal:
        _apply(device, BADLY_ORDERED_DECLARATION)

    assert refusal.value.errno == errno.EACCES
    assert device.read()[CONTROL_EXPOSURE_TIME_ABSOLUTE] == ARDUCAM_EXPOSURE_TIME_MINIMUM


def test_the_same_writes_in_the_planned_order_all_land() -> None:
    """The counterpart to the case above: the reordering is what keeps the writes from refusal."""
    device = arducam_control_set()
    plan = plan_control_writes(BADLY_ORDERED_DECLARATION, device.read())

    _apply(device, plan.ordered)

    assert verify_control_readback(plan, device.read()) == ()


def test_a_menu_entry_this_device_does_not_offer_is_refused_rather_than_clamped() -> None:
    """`auto_exposure` reports 0..3 and answers to 0 and 1, so 3 is in range and still not real.

    An integer control would have clamped 3 down to its ceiling and reported success. A menu
    does not, which is why the entry list is carried rather than derived from the bounds.
    """
    device = arducam_control_set()
    absent_entry = max(ARDUCAM_AUTO_EXPOSURE_MENU_ENTRIES) + 2

    with pytest.raises(OSError) as refusal:
        device.write(CONTROL_AUTO_EXPOSURE, absent_entry)

    assert refusal.value.errno == errno.EINVAL
    assert device.read()[CONTROL_AUTO_EXPOSURE] == ARDUCAM_AUTO_EXPOSURE_AUTO_MODE


def test_a_value_v4l2_clamps_is_refused_rather_than_run_silently() -> None:
    """9999 becomes 660 on this model, and the write that landed elsewhere reported success."""
    device = arducam_control_set()
    declared = (
        CameraControl(CONTROL_AUTO_EXPOSURE, ARDUCAM_AUTO_EXPOSURE_MANUAL),
        CameraControl(CONTROL_EXPOSURE_TIME_ABSOLUTE, 9999),
    )
    plan = plan_control_writes(declared, device.read())

    _apply(device, plan.ordered)
    mismatches = verify_control_readback(plan, device.read())

    assert [m.name for m in mismatches] == [CONTROL_EXPOSURE_TIME_ABSOLUTE]
    assert mismatches[0].actual == ARDUCAM_EXPOSURE_TIME_MAXIMUM
    with pytest.raises(CameraControlError, match="9999"):
        assert_controls_locked(mismatches, CAMERA_LABEL)


def test_a_control_this_device_does_not_have_is_skipped_and_named() -> None:
    """A ZED-M over UVC has no exposure controls; that is not a fault, but it is reported."""
    device = zed_uvc_control_set()

    plan = plan_control_writes(WRIST_CAMERA_CONTROLS, device.read())

    assert set(plan.skipped) == {
        CONTROL_AUTO_EXPOSURE,
        CONTROL_EXPOSURE_TIME_ABSOLUTE,
        CONTROL_GAIN,
    }
    _apply(device, plan.ordered)
    assert_controls_locked(verify_control_readback(plan, device.read()), CAMERA_LABEL)


def test_a_device_that_answered_with_no_controls_is_refused_rather_than_called_clean() -> None:
    """Reading nothing means the reader failed; treating it as "nothing to do" reports a green."""
    with pytest.raises(CameraControlError, match="v4l2-ctl"):
        plan_control_writes(WRIST_CAMERA_CONTROLS, {})


def test_the_declared_values_sit_inside_the_bounds_and_away_from_both_edges() -> None:
    """Guards the declaration against drifting onto an edge, at either end.

    The floor is where an unconfigured camera already sits, so a declaration that reached it
    would be indistinguishable from one that never landed; the ceiling is where a clamped write
    ends up. Both switches must also be off, or the two values above are held inactive and
    describe nothing the sensor is running at.
    """
    declared = {control.name: control.value for control in WRIST_CAMERA_CONTROLS}

    assert (
        ARDUCAM_EXPOSURE_TIME_MINIMUM
        < declared[CONTROL_EXPOSURE_TIME_ABSOLUTE]
        < ARDUCAM_EXPOSURE_TIME_MAXIMUM
    )
    assert ARDUCAM_GAIN_MINIMUM < declared[CONTROL_GAIN] < ARDUCAM_GAIN_MAXIMUM
    assert declared[CONTROL_AUTO_EXPOSURE] in ARDUCAM_AUTO_EXPOSURE_MENU_ENTRIES
    assert declared[CONTROL_AUTO_EXPOSURE] != ARDUCAM_AUTO_EXPOSURE_AUTO_MODE
    assert declared[CONTROL_WHITE_BALANCE_AUTOMATIC] == ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF


def test_the_fake_powers_up_holding_none_of_the_values_it_will_be_asked_for() -> None:
    """If the fake ever powers up already configured, every case above stops proving anything.

    Stated as a difference from the declaration rather than as a list of expected numbers,
    because the way this goes wrong is a stock value quietly being set to the declared one —
    which a per-control equality check would go on passing.
    """
    stock = arducam_control_set().read()

    for control in WRIST_CAMERA_CONTROLS:
        assert stock[control.name] != control.value, control.name
    assert stock[CONTROL_EXPOSURE_TIME_ABSOLUTE] == ARDUCAM_EXPOSURE_TIME_MINIMUM
    assert stock[CONTROL_GAIN] == ARDUCAM_GAIN_MINIMUM
    assert stock[CONTROL_AUTO_EXPOSURE] == ARDUCAM_AUTO_EXPOSURE_AUTO_MODE
    assert stock[CONTROL_WHITE_BALANCE_AUTOMATIC] == ARDUCAM_WHITE_BALANCE_AUTOMATIC_ON
    assert stock[CONTROL_WHITE_BALANCE_TEMPERATURE] == ARDUCAM_WHITE_BALANCE_TEMPERATURE_DEFAULT


def test_a_reading_taken_before_the_writes_is_not_rewritten_by_them() -> None:
    """A caller compares a before-reading against an after-reading; the two must stay distinct.

    If a reading tracked the device instead of snapshotting it, before and after would be the
    same object and every comparison drawn between them would pass without checking anything.
    """
    device = arducam_control_set()
    before = device.read()

    _apply(device, plan_control_writes(WRIST_CAMERA_CONTROLS, before).ordered)

    assert before[CONTROL_EXPOSURE_TIME_ABSOLUTE] == ARDUCAM_EXPOSURE_TIME_MINIMUM
    assert device.read()[CONTROL_EXPOSURE_TIME_ABSOLUTE] == ARDUCAM_EXPOSURE_TIME_ABSOLUTE


def test_a_negotiated_pixel_format_that_is_not_the_declared_one_is_reported() -> None:
    """This module streams YUYV only, so an MJPG answer means the budget used the wrong Bpp."""
    assert decode_fourcc(YUYV_FOURCC) == ARDUCAM_PIXEL_FORMAT

    finding = pixel_format_finding(ARDUCAM_PIXEL_FORMAT, MJPG_FOURCC)

    assert finding is not None
    assert "MJPG" in finding
    assert ARDUCAM_PIXEL_FORMAT in finding
    assert pixel_format_finding(ARDUCAM_PIXEL_FORMAT, YUYV_FOURCC) is None


def test_a_control_the_device_does_not_expose_cannot_be_written_to_the_fake() -> None:
    """Deciding what a device lacks is the plan's job; the fake must not absorb it instead."""
    device = zed_uvc_control_set()

    with pytest.raises(KeyError):
        device.write(CONTROL_EXPOSURE_TIME_ABSOLUTE, ARDUCAM_EXPOSURE_TIME_ABSOLUTE)


def test_gain_is_written_even_though_no_switch_guards_it() -> None:
    """Gain is ungated, so it must still appear in the plan rather than being filtered as one."""
    device = arducam_control_set()

    plan = plan_control_writes(WRIST_CAMERA_CONTROLS, device.read())
    _apply(device, plan.ordered)

    assert device.read()[CONTROL_GAIN] == ARDUCAM_GAIN
    assert verify_control_readback(plan, device.read()) == ()
