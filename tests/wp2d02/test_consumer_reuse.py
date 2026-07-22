"""WP-2D-02 consumes WP-2D-01: it installs the jog monitor and re-fixes through the jog IK.

These are the reuse edges the audit cares about — that there is one jog and one IK, not a
shadow copy. The guard is wired as the jog's own singularity monitor; the swivel changes
the arm only through the jog's ``seed``/``plan_pose`` and never holds a solver of its own.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from backend.cartesian_jog import (
    JogAxis,
    JogCommand,
    JogKind,
    build_cartesian_jog,
)
from backend.singularity import (
    ArmJacobian,
    ElbowSwivel,
    SingularityGuard,
    build_elbow_swivel,
    build_singularity_guard,
)


def test_guard_installs_itself_as_the_jog_singularity_monitor() -> None:
    jog = build_cartesian_jog()
    assert jog._singularity_monitor is None
    guard = build_singularity_guard(jog)
    # The jog now consults this guard's callback before every step.
    assert jog._singularity_monitor == guard._on_step


def test_build_singularity_guard_without_a_jog_is_unattached() -> None:
    guard = build_singularity_guard()
    assert isinstance(guard, SingularityGuard)
    # Evaluation needs no jog; installation is what a jog is for.
    metrics = guard.evaluate("right", np.array([0.0, 0.0, 0.0, np.pi / 2, 0.0, 0.0, 0.0]))
    assert metrics.velocity_scale > 0.0


def test_swivel_binds_to_the_jog_and_shares_no_second_solver() -> None:
    jog = build_cartesian_jog()
    swivel = build_elbow_swivel(jog)
    assert isinstance(swivel, ElbowSwivel)
    assert swivel._jog is jog
    assert isinstance(swivel._jacobian, ArmJacobian)


def test_swivel_moves_the_committed_pose_through_the_jog() -> None:
    # The swivel's only channel to the arm is the jog's committed state; after a swivel
    # the jog reports the new configuration, proving the swivel drove the jog, not a copy.
    jog = build_cartesian_jog()
    step = JogCommand(side="right", kind=JogKind.TRANSLATION, axis=JogAxis.Y, sign=-1)
    for _ in range(6):
        jog.step(step)
    before = jog.committed_solution()
    build_elbow_swivel(jog).swivel("right", 0.2)
    assert not np.array_equal(jog.committed_solution(), before)
