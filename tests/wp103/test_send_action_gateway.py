"""Acceptance ② / ⑯ — send_action is a real override, and it records both action channels.

- ② The enforcement point is a genuine method override on the Robot subclass, not a
  pipeline stage a caller could skip: any caller holding the follower as a `Robot`
  and calling `send_action` goes through the gateway, and the command is intercepted
  rather than passed straight to the bus.
- ⑯ Every decision records BOTH the pre-clamp request and the post-clamp accepted
  action; a frame that kept only one is refused (`00` §8.3), because a post-clamp-only
  record erases what intervention and clamp saturation would need.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from lerobot.robots.openarm_follower import OpenArmFollower
from lerobot.robots.robot import Robot

from backend.actuation import GateFrame, SafetyReason
from backend.calibration.schema import MOTOR_ORDER
from contracts.action import validate_frame
from contracts.units import Deg
from packages.lerobot_robot_openarm.openarm_follower_oa import OaOpenArmFollower


def test_send_action_is_a_real_override_not_the_stock_method() -> None:
    """The follower overrides the stock send_action rather than inheriting it (②)."""
    assert OaOpenArmFollower.send_action is not OpenArmFollower.send_action


def test_any_robot_caller_goes_through_the_gateway(
    make_follower: Callable[..., OaOpenArmFollower],
) -> None:
    """Called via a plain `Robot` handle, send_action is intercepted by the gateway (②)."""
    follower = make_follower()
    # An async client would hold the device only as a Robot; the override still fires.
    robot: Robot = follower
    big_command = {f"{motor}.pos": 45.0 for motor in MOTOR_ORDER}

    applied = robot.send_action(big_command)

    # The gateway intercepted: uncalibrated, it rejects with the zero reason and holds
    # at present rather than passing the 45° command straight to the bus.
    assert follower.last_gate_result is not None
    assert follower.last_gate_result.reason is SafetyReason.ZERO_UNCALIBRATED
    assert all(applied[f"{motor}.pos"] == 0.0 for motor in MOTOR_ORDER)
    # The call was recorded — proof it passed through the gateway, not around it.
    assert len(follower.gateway.frames) == 1


def test_gateway_runs_the_filter_on_a_calibrated_arm(
    make_follower: Callable[..., OaOpenArmFollower],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a calibrated arm the filter runs: a too-fast command holds at present (②)."""
    monkeypatch.setattr(OaOpenArmFollower, "is_calibrated", property(lambda _self: True))
    follower = make_follower()
    fast_command = {f"{motor}.pos": 30.0 for motor in MOTOR_ORDER}

    applied = follower.send_action(fast_command)

    assert follower.last_gate_result is not None
    # A 30° step in one control period exceeds the velocity limit, so the arm holds at
    # present — the filter ran, and this is not the zero rejection.
    assert follower.last_gate_result.reason is not SafetyReason.ZERO_UNCALIBRATED
    assert applied[f"{MOTOR_ORDER[0]}.pos"] == 0.0


def test_both_request_and_accepted_are_recorded(
    make_follower: Callable[..., OaOpenArmFollower],
) -> None:
    """Each recorded frame carries both the request and the accepted action (⑯)."""
    follower = make_follower()
    follower.send_action({f"{motor}.pos": 3.0 for motor in MOTOR_ORDER})

    frame = follower.gateway.frames[-1]
    assert len(frame.requested) == len(MOTOR_ORDER)
    assert len(frame.accepted) == len(MOTOR_ORDER)
    # The request the caller sent is preserved beside the accepted action.
    assert frame.requested[0] == Deg(3.0)


def test_post_clamp_only_frame_is_refused() -> None:
    """A frame that kept only the accepted action, dropping the request, is refused (⑯)."""
    # The CTR-ACT contract's frame check flags a post-clamp-only record.
    assert validate_frame(has_requested=False, has_accepted=True)
    assert validate_frame(has_requested=True, has_accepted=False)
    # And the gateway's frame is structurally two-sided: a one-sided one is
    # unconstructible, which is the stronger form of the same rule.
    assert set(GateFrame.__dataclass_fields__) == {"requested", "accepted"}


def test_both_channels_present_is_accepted() -> None:
    """A frame with both channels present is a valid record (⑯)."""
    assert validate_frame(has_requested=True, has_accepted=True) == ()
