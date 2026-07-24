"""CG-4B-03a — a bimanual-48 robot with a SmolVLA checkpoint is refused.

FR-INF-070: the checkpoint's input/output width must match the robot's
observation/action width, and a policy whose ceiling the robot's width can never
reach is structurally impossible. Bimanual + velocity/torque is a 48-dim observation,
and SmolVLA caps `observation.state` at 32 (read from its installed config via the
committed WP-4B-01 capability), so the load is refused twice over.
"""

from __future__ import annotations

import pytest

from backend.compat.policy_matrix.capability import introspect_capability
from backend.inference.load_preflight import (
    CheckpointProfile,
    LoadPreflight,
    LoadRefusedError,
    RefusalCode,
    RobotProfile,
)
from contracts.plugin.config import Side
from tests.wp4b03.support import matching_checkpoint


def test_bimanual_48_smolvla_refused() -> None:
    """CG-4B-03a: bimanual 48 + SmolVLA -> refused (dimension + policy ceiling)."""
    robot = RobotProfile.bimanual_profile(use_velocity_and_torque=True)
    assert robot.observation_dim() == 48

    # A SmolVLA checkpoint cannot have a 48-dim input (its ceiling is 32), so the
    # trained input width disagrees with the robot's 48.
    checkpoint = CheckpointProfile(input_dim=32, output_dim=16, policy_id="smolvla")

    verdict = LoadPreflight().check(checkpoint, robot)

    assert not verdict.allowed
    codes = {reason.code for reason in verdict.refusals}
    assert RefusalCode.DIMENSION_MISMATCH in codes
    assert RefusalCode.POLICY_DIM_UNREACHABLE in codes


def test_policy_ceiling_read_from_installed_config() -> None:
    """The 32 ceiling is READ from SmolVLA's config, not hardcoded (WP-4B-01 reuse).

    A robot width at or under the introspected ceiling carries no
    POLICY_DIM_UNREACHABLE reason, proving the refusal tracks the read number.
    """
    assert introspect_capability("smolvla").max_state_dim == 32

    # A single-arm velocity/torque robot is 24-dim, at or under the 32 ceiling.
    robot = RobotProfile.single(side=Side.RIGHT, use_velocity_and_torque=True)
    assert robot.observation_dim() == 24
    checkpoint = matching_checkpoint(robot, policy_id="smolvla")

    verdict = LoadPreflight().check(checkpoint, robot)

    assert verdict.allowed
    assert all(r.code is not RefusalCode.POLICY_DIM_UNREACHABLE for r in verdict.refusals)


def test_dimension_match_is_allowed() -> None:
    """A GR00T-shaped checkpoint matching a bimanual-48 robot loads (gate is not vacuous)."""
    robot = RobotProfile.bimanual_profile(use_velocity_and_torque=True)
    checkpoint = matching_checkpoint(robot, policy_id="groot")

    verdict = LoadPreflight().check(checkpoint, robot)

    assert verdict.allowed
    verdict.raise_if_refused()


def test_refused_verdict_raises() -> None:
    """A refused verdict raises `LoadRefusedError` so a caller cannot proceed silently."""
    robot = RobotProfile.bimanual_profile(use_velocity_and_torque=True)
    checkpoint = CheckpointProfile(input_dim=32, output_dim=16, policy_id="smolvla")

    verdict = LoadPreflight().check(checkpoint, robot)

    with pytest.raises(LoadRefusedError):
        verdict.raise_if_refused()
