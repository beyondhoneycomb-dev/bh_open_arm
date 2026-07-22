"""The three hard gates that must all hold before any command is sent (`02b` §2.3 ①/④).

Without a torque path injection cannot start (④); without an armed dry-run barrier real
transmission is forbidden; without a confirmed, in-range safe initial state the first
torque on a brakeless arm has no support (①). The gates are checked in that order, so the
most fundamental refusal wins when several fail at once.
"""

from __future__ import annotations

import pytest

from backend.excitation import (
    DryRunGateNotArmedError,
    SafeInitialState,
    TorquePathUnavailableError,
    UnsafeInitialStateError,
)
from tests.wp2b06.support import REST_POSE, build_context, healthy_observer


def _confirmed() -> SafeInitialState:
    return SafeInitialState(
        at_rest_pose=True,
        drop_zone_isolated=True,
        mechanically_supported=True,
        rest_positions_rad=REST_POSE,
    )


def test_no_torque_path_cannot_start() -> None:
    # 04: without the FR-MOT-058 torque path, tau cannot be applied — injection waits.
    context = build_context(healthy_observer(), torque_path_present=False)
    with pytest.raises(TorquePathUnavailableError):
        context.injector.start(_confirmed())


def test_dry_run_gate_not_armed_cannot_start() -> None:
    context = build_context(healthy_observer(), armed=False)
    with pytest.raises(DryRunGateNotArmedError):
        context.injector.start(_confirmed())


def test_torque_path_checked_before_dry_run_gate() -> None:
    # Both gates fail; the most fundamental (no torque path) is the one that surfaces.
    context = build_context(healthy_observer(), armed=False, torque_path_present=False)
    with pytest.raises(TorquePathUnavailableError):
        context.injector.start(_confirmed())


def test_unconfirmed_flag_cannot_start() -> None:
    context = build_context(healthy_observer())
    unconfirmed = SafeInitialState(
        at_rest_pose=True,
        drop_zone_isolated=False,
        mechanically_supported=True,
        rest_positions_rad=REST_POSE,
    )
    with pytest.raises(UnsafeInitialStateError, match="confirmed"):
        context.injector.start(unconfirmed)


def test_rest_pose_out_of_bounds_cannot_start() -> None:
    context = build_context(healthy_observer())
    out_of_bounds = SafeInitialState(
        at_rest_pose=True,
        drop_zone_isolated=True,
        mechanically_supported=True,
        rest_positions_rad=(5.0, 1.4, 0.0, 1.0, 0.0, 0.0, 0.0),  # joint1 past its bound
    )
    with pytest.raises(UnsafeInitialStateError, match="joint 0"):
        context.injector.start(out_of_bounds)


def test_rest_pose_in_v1_joint2_convention_cannot_start() -> None:
    # A joint2 angle in the v1 range but outside the v2 range would identify against a
    # shifted gravity term — the exact WP-2B-01 hazard the gate refuses.
    context = build_context(healthy_observer())
    v1_pose = SafeInitialState(
        at_rest_pose=True,
        drop_zone_isolated=True,
        mechanically_supported=True,
        rest_positions_rad=(0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0),  # below v2 joint2 min
    )
    with pytest.raises(UnsafeInitialStateError, match="joint2"):
        context.injector.start(v1_pose)


def test_all_gates_pass_completes_the_trajectory() -> None:
    context = build_context(healthy_observer())
    result = context.injector.start(_confirmed())
    assert result.status.value == "completed"
    assert context.torque_path is not None
    assert context.torque_path.commanded_indices == list(range(context.trajectory.sample_count))
