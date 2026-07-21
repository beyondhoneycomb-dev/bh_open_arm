"""Acceptance ② — a qpos-order-shuffled model yields identical FK by name.

Verifies the upstream claim that indices resolve at runtime by joint name and are
"robust to changes in MJCF qpos ordering": the shuffled twin genuinely moves every
arm joint's qpos index, yet FK evaluated by name is byte-identical to the canonical
model. Only code that hard-coded an index could tell the two models apart.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from sim.fkik.shuffle import (
    build_canonical_model,
    build_shuffled_model,
    fk_by_name,
    qpos_index_of,
)

_ARM_JOINTS = tuple(f"openarm_{side}_joint{i}" for side in ("left", "right") for i in range(1, 8))


def test_shuffle_moves_every_arm_qpos_index() -> None:
    canonical = build_canonical_model()
    shuffled = build_shuffled_model()
    for joint in _ARM_JOINTS:
        canonical_adr = qpos_index_of(canonical, joint)
        shuffled_adr = qpos_index_of(shuffled, joint)
        # The probe joint sits ahead of the arms, shifting each arm index up by one.
        assert shuffled_adr == canonical_adr + 1


def test_fk_is_identical_by_name_across_configs() -> None:
    canonical = build_canonical_model()
    shuffled = build_shuffled_model()
    rng = np.random.default_rng(0)
    worst = 0.0
    for _ in range(64):
        right = (rng.random(8) - 0.5).astype(float)
        left = (rng.random(8) - 0.5).astype(float)
        cr, cl = fk_by_name(canonical, right, left)
        sr, sl = fk_by_name(shuffled, right, left)
        worst = max(worst, float(np.abs(cr - sr).max()), float(np.abs(cl - sl).max()))
    # Same physics, same names, only the layout changed: FK must not move at all.
    assert worst < 1e-9


def test_every_arm_joint_name_resolves_in_both_models() -> None:
    canonical = build_canonical_model()
    shuffled = build_shuffled_model()
    for joint in _ARM_JOINTS:
        assert qpos_index_of(canonical, joint) >= 0
        assert qpos_index_of(shuffled, joint) >= 0
