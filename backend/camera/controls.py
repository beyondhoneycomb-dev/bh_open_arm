"""Declare what exposure and white balance a wrist camera is opened with, and prove it took.

An Arducam B0495 opened with no declaration sits at `exposure_time_absolute=5` and `gain=168`,
the floor of both, and both held inactive by the automatic modes that own them — so what the
sensor is really running at is not any number the device will report. The failure does not look
like a camera fault to anyone downstream; it looks like the detector is bad. So the values are
declared rather than inherited, and the declaration is checked rather than trusted.

Four properties of V4L2 shape everything here, and only the first of them is silent:

- An integer control clamps. A value outside its bounds is replaced with the nearest legal one
  and the write reports success: 9999 lands as 660 and 1 lands as 168 on this model. The camera
  then runs at an exposure nobody declared, visible only as a frame that is a bit dark. This is
  the property the readback check exists for, and it is the only one a caller cannot learn about
  from the write itself.
- A menu control refuses. `auto_exposure` is a menu, and this model offers two entries — 0
  `Auto Mode` and 1 `Manual Mode` — while `QUERYCTRL` still reports its range as 0..3. Writing 3
  is inside the reported bounds, names no entry, and comes back EINVAL rather than clamped. A
  menu value is therefore checked against the entry list, never against the bounds.
- A control guarded by an automatic mode carries `flags=inactive` while that mode is on, and a
  write to it comes back EACCES with the value untouched. `exposure_time_absolute` and
  `white_balance_temperature` are both guarded. The switches must therefore be written first,
  and `plan_control_writes` reorders to guarantee it — the ordering is not left to the order
  someone happened to list the controls in. Getting it wrong does not quietly produce a wrong
  exposure; it produces a failed write, which a caller has to have somewhere to put.
- The control set differs per camera. The B0495 has no focus control at all (fixed M12 lens)
  and the ZED-M exposes no exposure controls over UVC — no `auto_exposure`, no
  `exposure_time_absolute`, no camera-class controls of any kind. A name the device does not
  have is not a fault; it is skipped and named in the plan.

Failure direction differs per operation, and the split is by what a wrong value costs:

- A readback mismatch is refused. The device could be rewritten, but frames already captured
  under a wrong exposure cannot — the sensor discarded the information at capture, into
  clipping at one end and into the noise floor at the other, and no gamma or contrast pass
  brings it back. Refusing before the stream opens costs one message; continuing costs every
  episode recorded until someone notices.
- A control the device does not expose is skipped and reported. It is that device's only
  possible answer, and its name survives into the plan.
- An empty readback is refused rather than passed. Reading nothing means the reader failed, not
  that the device has no controls, and nothing can be concluded from a measurement that did not
  happen. This is the one place worth stating plainly, because treating an empty read as "no
  work to do" is what turns "never verified" into a green result.
- A negotiated pixel format that is not the declared one is reported only. The negotiated
  format is the driver's to choose and `06` FR-CAM-071 fixes the direction as a warning;
  refusing would keep a working camera closed. `pixel_format_finding` returns the finding so a
  caller that wants a refusal can raise on it.

Nothing here opens a camera. This repository has no camera-opening call path yet — the values
are declared and the verification is pure, so both halves are exercised without hardware and
the seam can be wired up when one exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.camera.constants import (
    ARDUCAM_AUTO_EXPOSURE_MANUAL,
    ARDUCAM_EXPOSURE_TIME_ABSOLUTE,
    ARDUCAM_GAIN,
    ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF,
    ARDUCAM_WHITE_BALANCE_TEMPERATURE_K,
    AUTO_SWITCH_NAME_INFIX,
    AUTO_SWITCH_NAME_PREFIX,
    CONTROL_AUTO_EXPOSURE,
    CONTROL_EXPOSURE_TIME_ABSOLUTE,
    CONTROL_GAIN,
    CONTROL_WHITE_BALANCE_AUTOMATIC,
    CONTROL_WHITE_BALANCE_TEMPERATURE,
    FOURCC_CHARACTER_BITS,
    FOURCC_CHARACTER_COUNT,
)


class CameraControlError(RuntimeError):
    """A camera's controls could not be confirmed to hold the declared values."""


@dataclass(frozen=True)
class CameraControl:
    """One V4L2 control and the value it is declared to hold.

    Attributes:
        name: The control name as `v4l2-ctl -L` spells it.
        value: The declared value, in the control's own units.
    """

    name: str
    value: int


@dataclass(frozen=True)
class ControlWritePlan:
    """The writes to make on one device, in an order the device will honour.

    Attributes:
        ordered: The writes to perform, automatic-mode switches first.
        skipped: Declared names this device does not expose, kept so a skip is reported
            rather than silent.
    """

    ordered: tuple[CameraControl, ...]
    skipped: tuple[str, ...]


@dataclass(frozen=True)
class ControlMismatch:
    """A control that read back as something other than what was written.

    Attributes:
        name: The control name.
        declared: The value the plan asked for.
        actual: The value the device reports holding.
    """

    name: str
    declared: int
    actual: int


# Manual exposure and manual white balance, at values measured to hold detail on this model.
# The switches are listed first for a reader's benefit only; `plan_control_writes` does not
# trust this order, and a test reverses this tuple to prove it.
WRIST_CAMERA_CONTROLS: tuple[CameraControl, ...] = (
    CameraControl(CONTROL_AUTO_EXPOSURE, ARDUCAM_AUTO_EXPOSURE_MANUAL),
    CameraControl(CONTROL_WHITE_BALANCE_AUTOMATIC, ARDUCAM_WHITE_BALANCE_AUTOMATIC_OFF),
    CameraControl(CONTROL_EXPOSURE_TIME_ABSOLUTE, ARDUCAM_EXPOSURE_TIME_ABSOLUTE),
    CameraControl(CONTROL_GAIN, ARDUCAM_GAIN),
    CameraControl(CONTROL_WHITE_BALANCE_TEMPERATURE, ARDUCAM_WHITE_BALANCE_TEMPERATURE_K),
)


def _is_auto_switch(name: str) -> bool:
    """Report whether a control name is an automatic-mode switch guarding another control."""
    return name.startswith(AUTO_SWITCH_NAME_PREFIX) or AUTO_SWITCH_NAME_INFIX in name


def plan_control_writes(
    declared: Sequence[CameraControl],
    present: Mapping[str, int],
) -> ControlWritePlan:
    """Order the declared writes so no write lands on a control that is still inactive.

    Args:
        declared: The controls this camera is declared to hold.
        present: Control name to current value, as read from the device. Membership is what
            decides whether the device has a control at all.

    Returns:
        (ControlWritePlan) The writes to make, automatic-mode switches first and declaration
        order preserved within each group, plus the names this device does not expose.

    Raises:
        CameraControlError: If `present` is empty. A UVC camera exposes controls; reading none
            means the read failed, and a plan built on it would report success for writes
            nothing ever checked.
    """
    if not present:
        raise CameraControlError(
            "this device reported no controls at all, so nothing about its exposure or white "
            "balance can be confirmed. A UVC camera exposes controls — an empty answer means "
            "the read failed, not that there is nothing to set. Check that v4l2-ctl is "
            "installed (`apt install v4l-utils`) and that `v4l2-ctl -d <device> -L` answers, "
            "rather than opening the camera unverified"
        )
    switches = tuple(c for c in declared if c.name in present and _is_auto_switch(c.name))
    guarded = tuple(c for c in declared if c.name in present and not _is_auto_switch(c.name))
    return ControlWritePlan(
        ordered=switches + guarded,
        skipped=tuple(c.name for c in declared if c.name not in present),
    )


def verify_control_readback(
    plan: ControlWritePlan,
    after: Mapping[str, int],
) -> tuple[ControlMismatch, ...]:
    """Compare what the plan asked for against what the device reports after the writes.

    Args:
        plan: The plan that was applied.
        after: Control name to value, re-read from the device.

    Returns:
        (tuple[ControlMismatch, ...]) One entry per control now holding something other than
        the declared value, empty when every write took.
    """
    return tuple(
        ControlMismatch(name=control.name, declared=control.value, actual=after[control.name])
        for control in plan.ordered
        if after[control.name] != control.value
    )


def assert_controls_locked(
    mismatches: Sequence[ControlMismatch],
    camera_label: str,
) -> None:
    """Refuse a camera whose controls did not take the declared values.

    Args:
        mismatches: The mismatches found by `verify_control_readback`.
        camera_label: Human-readable camera identifier for the message.

    Raises:
        CameraControlError: If any control reads back differently. The message carries every
            name with both values, because the difference is invisible in the frames.
    """
    if not mismatches:
        return
    detail = "; ".join(f"{m.name}: asked {m.declared}, device holds {m.actual}" for m in mismatches)
    raise CameraControlError(
        f"{camera_label} did not take its declared controls — {detail}. A write that reached an "
        "integer control and landed somewhere else was clamped into that control's bounds and "
        "reported success; the refusals (EACCES on a control an automatic mode still guards, "
        "EINVAL on a menu entry the device does not have) raise at the write instead and never "
        "reach here. Read `v4l2-ctl -d <device> -L` for the accepted range before recording, "
        "because a wrong exposure only looks like a slightly dark frame"
    )


def decode_fourcc(code: int) -> str:
    """Render a packed FOURCC word as its four characters.

    Args:
        code: The 32-bit FOURCC as the capture backend reports it.

    Returns:
        (str) The format name, e.g. `YUYV`.
    """
    return "".join(
        chr((code >> (FOURCC_CHARACTER_BITS * position)) & 0xFF)
        for position in range(FOURCC_CHARACTER_COUNT)
    )


def pixel_format_finding(declared: str, negotiated_code: int) -> str | None:
    """Report a negotiated pixel format that is not the declared one.

    A finding rather than a refusal: the driver picks the format it can deliver, and
    `06` FR-CAM-071 fixes this as a warning. It matters because the bandwidth budget is
    computed from bytes-per-pixel, which is a property of the format that was negotiated and
    not of the one that was asked for.

    Args:
        declared: The format the configuration asked for.
        negotiated_code: The FOURCC the backend actually negotiated.

    Returns:
        (str | None) A finding naming both formats, or None when they agree.
    """
    negotiated = decode_fourcc(negotiated_code)
    if negotiated == declared:
        return None
    return (
        f"negotiated pixel format {negotiated!r} is not the declared {declared!r}; the "
        "bandwidth budget for this camera was computed from the declared format's "
        "bytes-per-pixel and no longer describes what it draws"
    )
