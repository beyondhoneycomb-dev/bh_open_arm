"""Why LeRobot's joint_limits clipping is void in torque mode, and the proof it is (WP-2D-04).

`04` FR-MAN-036: LeRobot's `joint_limits` clip applies to the `.pos` command only
(`openarm_follower.py:288-297`), so in Freedrive — which drives the MIT `tau` channel, not a
position command — the clip touches nothing. It is fully void, and the joint limits are held
instead by the repulsion torque (`repulsion`). Acceptance ④ requires that voidness to be a
tested fact, not an assumption.

This module supplies the honest proof surface. `modeled_lerobot_position_clip` reproduces the
documented `.pos` clamp — a plain min/max to the bounds — purely so a test can show what that
clip does to a position. It is **not** an enforcement path: LeRobot owns the real clip and the
Freedrive tau path never routes through any position clamp. `position_clip_is_void` states the
consequence: for any angle already within its limits the clamp is the identity, so it applies
no restoring action and cannot keep a hand-guided joint off its hardstop — the repulsion torque
does, on a channel the position clip does not touch.
"""

from __future__ import annotations

# The invariant, as a first-class label so a test and a reader read one statement of it: the
# position clip is a position-channel operation, and Freedrive commands torque, so the clip is
# void in torque mode and the wall torque is what enforces the limit.
POSITION_CLIP_VOID_IN_TORQUE_MODE_NOTE = (
    "LeRobot joint_limits clips the .pos command only; Freedrive drives the tau channel, so "
    "the position clip is fully void in torque mode and the joint limit is held by the "
    "repulsion torque (04 FR-MAN-036)"
)


def modeled_lerobot_position_clip(pos_rad: float, lower_rad: float, upper_rad: float) -> float:
    """Reproduce LeRobot's documented `.pos` clamp, for the void proof only.

    This is a model of the upstream position clip (`04` FR-MAN-036: `.pos`-key clamp to the
    bounds), not an enforcement path — the Freedrive tau path never calls a position clamp.
    It exists so a test can show the clamp is the identity within the limits.

    Args:
        pos_rad: The position command, radians.
        lower_rad: The lower joint limit, radians.
        upper_rad: The upper joint limit, radians.

    Returns:
        (float) The position clamped to [lower_rad, upper_rad].
    """
    return max(lower_rad, min(upper_rad, pos_rad))


def position_clip_is_void(pos_rad: float, lower_rad: float, upper_rad: float) -> bool:
    """Whether the position clip leaves an angle unchanged (applies no restoring action).

    True for any angle already within its limits: the clamp is the identity there, so it
    provides no force to keep a hand-guided joint off its hardstop. That is the sense in which
    LeRobot's clip is void in torque mode — the repulsion torque, not the clip, does the work.

    Args:
        pos_rad: The joint angle, radians.
        lower_rad: The lower joint limit, radians.
        upper_rad: The upper joint limit, radians.

    Returns:
        (bool) True when the clamp does not alter the angle.
    """
    return modeled_lerobot_position_clip(pos_rad, lower_rad, upper_rad) == pos_rad
