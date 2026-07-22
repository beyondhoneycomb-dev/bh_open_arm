"""Negative branch (02b §4.2) — a taught point must not silently replay after a zero
procedure change: the same joint angles are then a different pose (FAIL_BLOCKING).

Two proofs, one structural and one physical:

- The store offers no way to obtain a replay set without passing the current zero
  identity through the gate, so a stale point cannot reach a replay path unseen; it
  lands in ``blocked`` with a warning and never in ``replayable``.
- The hazard the gate prevents is real, not bureaucratic: commanding the same stored
  ``q_urdf`` after the zero reference has moved lands the EE at a measurably different
  pose. This is shown through the reused WP-2D-01 FK over the committed cell asset — no
  second kinematics.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from backend.teaching import (
    ReplayDecision,
    TeachingPointStore,
)

from . import RIGHT, ZEROED_AT_A, ZEROED_AT_B, identity, make_point

# The joint-space shift a re-zero introduces on one shoulder joint. It stands in for
# the physical consequence the new zeroed_at witnesses: the same command now lands the
# arm a few centimetres away.
_REZERO_SHIFT_RAD = 0.1
_SHIFTED_JOINT = 1
_MIN_POSE_DIVERGENCE_M = 0.01


def test_replay_accessors_all_require_a_current_zero_identity() -> None:
    # There is no door to a replay set that skips the gate: every accessor that yields
    # postures for replay demands the current identity to check them against.
    for method_name in ("replay_verdicts", "replayable", "blocked"):
        signature = inspect.signature(getattr(TeachingPointStore, method_name))
        assert "current" in signature.parameters, method_name


def test_stale_point_is_blocked_and_never_replayable_after_rezero() -> None:
    store = TeachingPointStore(RIGHT)
    store.add(make_point("taught_at_A", zero=identity(RIGHT, zeroed_at=ZEROED_AT_A)))

    current = identity(RIGHT, zeroed_at=ZEROED_AT_B)
    assert store.replayable(current) == ()
    blocked = store.blocked(current)
    assert [p.name for p, _ in blocked] == ["taught_at_A"]
    assert blocked[0][1].decision is ReplayDecision.BLOCKED
    assert blocked[0][1].reason  # a non-empty operator warning, not a silent drop


def test_same_joint_command_reaches_a_different_pose_after_rezero() -> None:
    pytest.importorskip("mujoco")
    pytest.importorskip("mink")
    pytest.importorskip("lerobot")
    from backend.cartesian_jog import KinematicFrames

    frames = KinematicFrames()
    q_lift = 0.15
    q_command = [0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.0]

    taught = np.concatenate([np.array(q_command, dtype=float), np.zeros(8)])
    pose_taught = frames.control_point_pose(RIGHT, taught, q_lift)

    # The same command, but the zero reference has moved: physically the arm now sits a
    # shift away on the re-zeroed joint. FK of that posture is the pose a naive replay
    # would actually reach.
    q_after = list(q_command)
    q_after[_SHIFTED_JOINT] += _REZERO_SHIFT_RAD
    after = np.concatenate([np.array(q_after, dtype=float), np.zeros(8)])
    pose_after = frames.control_point_pose(RIGHT, after, q_lift)

    divergence = float(np.linalg.norm(pose_after[:3] - pose_taught[:3]))
    assert divergence > _MIN_POSE_DIVERGENCE_M

    # And the gate refuses to let that happen silently: the point taught under the old
    # zero is blocked once the record reads the re-zero.
    point = make_point("taught_at_A", q_urdf=q_command, zero=identity(RIGHT, zeroed_at=ZEROED_AT_A))
    store = TeachingPointStore(RIGHT)
    store.add(point)
    assert store.replayable(identity(RIGHT, zeroed_at=ZEROED_AT_B)) == ()
