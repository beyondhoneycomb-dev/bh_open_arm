"""Acceptance ①–⑤ — the dimension axis blocks over-ceiling, never over-blocks.

A bimanual + velocity/torque recording is 48-dim; the 32-capped policies
(SmolVLA/pi0/pi05) must be BLOCKED against it with the exact reason
`state_dim 48 > max_state_dim 32`, GR00T (132-dim ceiling) must be accepted, and a
24-dim single-arm recording must not be over-blocked for SmolVLA.
"""

from __future__ import annotations

import pytest

from backend.policy_matrix import DatasetObsConfig, DeployRequest, build_matrix
from backend.policy_matrix.matrix import AXIS_DIMENSION

# rtx_5090 + async isolates the dimension axis: no frequency ceiling is measured for
# it (targets.guards.INFERENCE_CEILING_HZ), and async never touches the sync guard,
# so any block on these cells comes from the dimension axis alone.
_DEPLOY = DeployRequest(target_id="rtx_5090", mode="async")
_BIMANUAL_48 = DatasetObsConfig(bimanual=True, use_velocity_and_torque=True)
_UNIMANUAL_24 = DatasetObsConfig(bimanual=False, use_velocity_and_torque=True)


@pytest.fixture(scope="module")
def matrix():  # type: ignore[no-untyped-def]
    """The calculator over the on-disk registry and target matrix."""
    return build_matrix()


@pytest.mark.parametrize("policy", ["smolvla", "pi0", "pi05"])
def test_bimanual_48_over_ceiling_is_blocked(matrix, policy) -> None:  # type: ignore[no-untyped-def]
    """①②③ — 48-dim x a 32-capped policy is blocked with the exact reason."""
    cell = matrix.evaluate(_BIMANUAL_48, policy, _DEPLOY)
    assert not cell.allowed
    dimension_blocks = [b for b in cell.blocks if b.axis == AXIS_DIMENSION]
    assert len(dimension_blocks) == 1
    assert dimension_blocks[0].human == "state_dim 48 > max_state_dim 32"
    assert dimension_blocks[0].code == "STATE_DIM_OVER_CAP"


def test_bimanual_48_fits_groot(matrix) -> None:  # type: ignore[no-untyped-def]
    """④ — GR00T's 132-dim ceiling accepts the 48-dim state."""
    cell = matrix.evaluate(_BIMANUAL_48, "groot", _DEPLOY)
    assert cell.allowed
    assert cell.blocks == ()


def test_unimanual_24_is_not_over_blocked(matrix) -> None:  # type: ignore[no-untyped-def]
    """⑤ — a 24-dim recording fits SmolVLA's 32-dim ceiling; no over-block."""
    cell = matrix.evaluate(_UNIMANUAL_24, "smolvla", _DEPLOY)
    assert cell.allowed


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
