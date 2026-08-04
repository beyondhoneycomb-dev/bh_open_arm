"""Exposure and white balance: that the declaration is ordered by the device's rules, not ours.

Every case runs against `FakeCameraControls`, which reproduces the two silent behaviours the
readback check exists to catch — a value clamped into range without complaint, and a write
discarded because the control's automatic mode still guards it. Those two behaviours carry the
weight here: a fake that accepted every write would let the whole comparison pass while
verifying nothing, so two of the cases below are written to die if the fake ever softens.

Nothing here needs a camera. What still needs one is the declaration itself — 60 / 200 / 4000 K
were measured on a sibling rig under its lighting, and `PG-CAM-001` re-measures them on this
bench. There is no hardware case in this file because there is no captured `v4l2-ctl -L` output
to check a reader against yet; writing one against imagined output would prove only that the
guess is self-consistent.
"""

from __future__ import annotations

import pytest

from backend.camera.constants import (
    ARDUCAM_EXPOSURE_TIME_ABSOLUTE,
    ARDUCAM_GAIN,
    ARDUCAM_PIXEL_FORMAT,
    ARDUCAM_STOCK_EXPOSURE_TIME_ABSOLUTE,
    ARDUCAM_STOCK_GAIN,
    ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF,
    ARDUCAM_WHITE_BALANCE_TEMPERATURE_K,
    AUTO_EXPOSURE_APERTURE_PRIORITY,
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
# after the control it guards — the order the device silently discards.
BADLY_ORDERED_DECLARATION = (
    CameraControl(CONTROL_EXPOSURE_TIME_ABSOLUTE, ARDUCAM_EXPOSURE_TIME_ABSOLUTE),
    CameraControl(CONTROL_AUTO_EXPOSURE, 1),
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


def test_a_write_made_while_its_auto_switch_is_on_is_caught_as_a_mismatch() -> None:
    """Written in the bad order, exposure never lands — and the device says nothing about it."""
    device = arducam_control_set()
    plan = plan_control_writes(BADLY_ORDERED_DECLARATION, device.read())

    _apply(device, BADLY_ORDERED_DECLARATION)
    mismatches = verify_control_readback(plan, device.read())

    assert [m.name for m in mismatches] == [CONTROL_EXPOSURE_TIME_ABSOLUTE]
    assert mismatches[0].declared == ARDUCAM_EXPOSURE_TIME_ABSOLUTE
    assert mismatches[0].actual == ARDUCAM_STOCK_EXPOSURE_TIME_ABSOLUTE
    with pytest.raises(CameraControlError, match=CONTROL_EXPOSURE_TIME_ABSOLUTE):
        assert_controls_locked(mismatches, CAMERA_LABEL)


def test_the_same_writes_in_the_planned_order_all_land() -> None:
    """The counterpart to the case above: the reordering is what makes the writes take."""
    device = arducam_control_set()
    plan = plan_control_writes(BADLY_ORDERED_DECLARATION, device.read())

    _apply(device, plan.ordered)

    assert verify_control_readback(plan, device.read()) == ()


def test_a_value_v4l2_clamps_is_refused_rather_than_run_silently() -> None:
    """9999 becomes 660 on this model, and 660 is the maximum that clips frames to white."""
    device = arducam_control_set()
    declared = (
        CameraControl(CONTROL_AUTO_EXPOSURE, 1),
        CameraControl(CONTROL_EXPOSURE_TIME_ABSOLUTE, 9999),
    )
    plan = plan_control_writes(declared, device.read())

    _apply(device, plan.ordered)
    mismatches = verify_control_readback(plan, device.read())

    assert [m.name for m in mismatches] == [CONTROL_EXPOSURE_TIME_ABSOLUTE]
    assert mismatches[0].actual == ARDUCAM_STOCK_EXPOSURE_TIME_ABSOLUTE
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


def test_the_declared_values_sit_off_the_clipping_edge() -> None:
    """Guards the declaration itself against being reset to the maxima a camera powers up at."""
    declared = {control.name: control.value for control in WRIST_CAMERA_CONTROLS}

    assert declared[CONTROL_EXPOSURE_TIME_ABSOLUTE] < ARDUCAM_STOCK_EXPOSURE_TIME_ABSOLUTE
    assert declared[CONTROL_GAIN] < ARDUCAM_STOCK_GAIN
    assert declared[CONTROL_AUTO_EXPOSURE] != AUTO_EXPOSURE_APERTURE_PRIORITY
    assert declared[CONTROL_WHITE_BALANCE_AUTOMATIC] == ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF


def test_the_stock_state_is_the_clipping_one_the_declaration_is_written_against() -> None:
    """If the fake ever powers up already configured, every case above stops proving anything."""
    stock = arducam_control_set().read()

    assert stock[CONTROL_EXPOSURE_TIME_ABSOLUTE] == ARDUCAM_STOCK_EXPOSURE_TIME_ABSOLUTE
    assert stock[CONTROL_GAIN] == ARDUCAM_STOCK_GAIN
    assert stock[CONTROL_AUTO_EXPOSURE] == AUTO_EXPOSURE_APERTURE_PRIORITY


def test_a_reading_taken_before_the_writes_is_not_rewritten_by_them() -> None:
    """A caller compares a before-reading against an after-reading; the two must stay distinct.

    If a reading tracked the device instead of snapshotting it, before and after would be the
    same object and every comparison drawn between them would pass without checking anything.
    """
    device = arducam_control_set()
    before = device.read()

    _apply(device, plan_control_writes(WRIST_CAMERA_CONTROLS, before).ordered)

    assert before[CONTROL_EXPOSURE_TIME_ABSOLUTE] == ARDUCAM_STOCK_EXPOSURE_TIME_ABSOLUTE
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
