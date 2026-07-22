"""Acceptance ② `buttons[1]` squeeze analog, and ③ the `axes.length >= 4` joystick guard."""

from __future__ import annotations

import pytest

from backend.teleop.webxr.constants import MIN_AXES_FOR_THUMBSTICK, XR_STANDARD_MAPPING
from backend.teleop.webxr.gamepad import (
    GamepadState,
    read_face_buttons,
    read_squeeze,
    read_thumbstick,
    read_trigger,
    thumbstick_transmittable,
)
from backend.teleop.webxr.profiles import XR_STANDARD_LAYOUT

_LAYOUT = XR_STANDARD_LAYOUT


def test_squeeze_reads_buttons_index_one_as_analog() -> None:
    # ②: the clutch input is the analog value at buttons[1], not a pressed boolean.
    state = GamepadState(
        buttons=[0.1, 0.73, 0.0, 0.0, 0.0, 0.0],
        axes=[0.0, 0.0, 0.0, 0.0],
        mapping=XR_STANDARD_MAPPING,
    )
    assert read_squeeze(state, _LAYOUT) == pytest.approx(0.73)
    assert read_trigger(state, _LAYOUT) == pytest.approx(0.1)


def test_squeeze_preserves_partial_grip() -> None:
    # A partial grip must survive as an analog value for the downstream clutch threshold.
    for value in (0.0, 0.25, 0.5, 0.9, 1.0):
        state = GamepadState(
            buttons=[0.0, value], axes=[0.0, 0.0, 0.0, 0.0], mapping=XR_STANDARD_MAPPING
        )
        assert read_squeeze(state, _LAYOUT) == pytest.approx(value)


def test_face_buttons_read_indices_four_and_five() -> None:
    state = GamepadState(
        buttons=[0.0, 0.0, 0.0, 0.0, 0.8, 0.6],
        axes=[0.0, 0.0, 0.0, 0.0],
        mapping=XR_STANDARD_MAPPING,
    )
    face = read_face_buttons(state, _LAYOUT)
    assert face.primary == pytest.approx(0.8)
    assert face.secondary == pytest.approx(0.6)


def test_joystick_guard_requires_four_axes() -> None:
    # ③: the guard is on the axis COUNT. Fewer than four axes -> no stick to send.
    assert MIN_AXES_FOR_THUMBSTICK == 4
    for count in range(MIN_AXES_FOR_THUMBSTICK):
        state = GamepadState(buttons=[0.0, 0.0], axes=[0.5] * count, mapping=XR_STANDARD_MAPPING)
        assert thumbstick_transmittable(state) is False
        assert read_thumbstick(state, _LAYOUT) is None


def test_thumbstick_reads_axes_two_and_three() -> None:
    # ③: with the guard cleared, the stick is axes[2]/axes[3].
    state = GamepadState(
        buttons=[0.0, 0.0], axes=[0.0, 0.0, 0.42, -0.17], mapping=XR_STANDARD_MAPPING
    )
    stick = read_thumbstick(state, _LAYOUT)
    assert stick is not None
    assert stick.x == pytest.approx(0.42)
    assert stick.y == pytest.approx(-0.17)


def test_zero_leading_axes_do_not_suppress_the_stick() -> None:
    # The upstream falsy guard suppressed the stick when axes[0]/[1] were 0 (Touch Plus
    # has no touchpad). The count guard transmits regardless of leading-axis values.
    state = GamepadState(buttons=[0.0, 0.0], axes=[0.0, 0.0, 0.9, 0.9], mapping=XR_STANDARD_MAPPING)
    stick = read_thumbstick(state, _LAYOUT)
    assert stick is not None
    assert (stick.x, stick.y) == pytest.approx((0.9, 0.9))


def test_more_than_four_axes_still_reads_indices_two_and_three() -> None:
    state = GamepadState(
        buttons=[0.0, 0.0], axes=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6], mapping=XR_STANDARD_MAPPING
    )
    stick = read_thumbstick(state, _LAYOUT)
    assert stick is not None
    assert (stick.x, stick.y) == pytest.approx((0.3, 0.4))
