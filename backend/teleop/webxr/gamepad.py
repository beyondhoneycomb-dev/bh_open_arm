"""Gamepad reads over a resolved xr-standard layout (WP-3B-08 ② and ③).

Two upstream reads are wrong and this module fixes both, indexing every read through
the resolved `ControllerLayout` so a role (`squeeze`, `thumbstick`) is never a bare
integer at the call site:

- ② `buttons[1]` (squeeze/grip) is read as an analog value. Upstream `ar.js` never
  reads it, so the clutch has no input (`05` §2.7 ⓑ, `FR-TEL-018`). A WebXR gamepad
  button is an object carrying an analog `.value` in `[0, 1]`; this module models a
  button as that already-extracted float.
- ③ the joystick is guarded on `axes.length >= 4`, not on the axis values. Upstream
  `if (axes[0] && axes[1] && axes[2] && axes[3])` treats a legitimately-zero axis as
  "no stick" — Touch Plus has no touchpad, so `axes[0]/[1]` are always 0 and the
  stick is never sent (`05` §2.7 ⓒ, `FR-TEL-019`). Here the guard is purely on the
  axis COUNT, and the stick is read from `axes[2]/[3]`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.teleop.webxr.constants import MIN_AXES_FOR_THUMBSTICK
from backend.teleop.webxr.profiles import ControllerLayout


@dataclass(frozen=True)
class GamepadState:
    """One sampled WebXR gamepad: analog buttons, axes, and the mapping string.

    Attributes:
        buttons: Per-button analog `.value` readings, in gamepad index order.
        axes: Per-axis readings in `[-1, 1]`, in gamepad index order.
        mapping: The gamepad `mapping` string (e.g. `xr-standard`).
    """

    buttons: Sequence[float]
    axes: Sequence[float]
    mapping: str


@dataclass(frozen=True)
class Thumbstick:
    """A thumbstick reading from `axes[2]/[3]`.

    Attributes:
        x: The x axis (`axes[2]`).
        y: The y axis (`axes[3]`).
    """

    x: float
    y: float


@dataclass(frozen=True)
class FaceButtons:
    """The two face-button analog readings (A·B or X·Y), from `buttons[4]/[5]`.

    Attributes:
        primary: The A/X button (`buttons[4]`).
        secondary: The B/Y button (`buttons[5]`).
    """

    primary: float
    secondary: float


def _button(state: GamepadState, index: int) -> float:
    """Return the analog value of a button, or 0.0 when the index is absent.

    An absent button is reported as released rather than raised: a controller with a
    shorter button array is a real WebXR case, and a missing optional button is not a
    fault the read layer should turn into an exception.
    """
    return state.buttons[index] if index < len(state.buttons) else 0.0


def read_trigger(state: GamepadState, layout: ControllerLayout) -> float:
    """Read the trigger analog value (`buttons[0]`).

    Args:
        state: The sampled gamepad.
        layout: The resolved controller layout.

    Returns:
        (float) The trigger value in `[0, 1]`.
    """
    return _button(state, layout.trigger_button_index)


def read_squeeze(state: GamepadState, layout: ControllerLayout) -> float:
    """Read the squeeze/grip analog value (`buttons[1]`) — acceptance ②.

    This is the clutch input the upstream path never reads. It is the analog `.value`,
    not a pressed/not-pressed boolean, so a partial grip is preserved for the
    downstream clutch threshold (`WP-3B-09`).

    Args:
        state: The sampled gamepad.
        layout: The resolved controller layout.

    Returns:
        (float) The squeeze value in `[0, 1]`.
    """
    return _button(state, layout.squeeze_button_index)


def read_face_buttons(state: GamepadState, layout: ControllerLayout) -> FaceButtons:
    """Read the two face-button analog values (`buttons[4]/[5]`).

    Args:
        state: The sampled gamepad.
        layout: The resolved controller layout.

    Returns:
        (FaceButtons) The primary (A/X) and secondary (B/Y) readings.
    """
    return FaceButtons(
        primary=_button(state, layout.primary_face_button_index),
        secondary=_button(state, layout.secondary_face_button_index),
    )


def thumbstick_transmittable(state: GamepadState) -> bool:
    """Report whether the joystick send guard passes — acceptance ③.

    The guard is purely on the axis COUNT: the thumbstick lives at `axes[2]/[3]`, so
    the gamepad must expose at least four axes. It never inspects the axis values, so
    a legitimately-zero axis does not suppress transmission.

    Args:
        state: The sampled gamepad.

    Returns:
        (bool) True when at least `MIN_AXES_FOR_THUMBSTICK` axes are present.
    """
    return len(state.axes) >= MIN_AXES_FOR_THUMBSTICK


def read_thumbstick(state: GamepadState, layout: ControllerLayout) -> Thumbstick | None:
    """Read the thumbstick from `axes[2]/[3]`, guarded on `axes.length >= 4`.

    Args:
        state: The sampled gamepad.
        layout: The resolved controller layout.

    Returns:
        (Thumbstick | None) The `(axes[2], axes[3])` reading, or None when the guard
        fails (fewer than four axes) — the honest "no stick to send" signal.
    """
    if not thumbstick_transmittable(state):
        return None
    return Thumbstick(
        x=state.axes[layout.thumbstick_x_axis_index],
        y=state.axes[layout.thumbstick_y_axis_index],
    )
