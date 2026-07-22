"""Acceptance ② — the residual-disable reason is the model/offset pair, not "no torque".

FR-SAF-024 (reason replaced, conclusion kept): the gripper's torque IS observed, so the
reason the gripper is excluded from residual detection must be ① no finger dynamics
model and ② grasp reaction = constant torque offset — never "no torque observation".
The reason reuses WP-2B-01's single `GRIPPER_MODEL_REASON`, so the two facts have one
owner and cannot drift.
"""

from __future__ import annotations

from backend.dynamics.constants import GRIPPER_MODEL_REASON
from backend.temp_gripper.constants import GRIPPER_TORQUE_IS_OBSERVED
from backend.temp_gripper.residual_policy import (
    GRIPPER_RESIDUAL_DISABLED_REASON,
    gripper_torque_is_observed,
)

# Phrases a wrong (v1 ros2_control) rationale would use; the reason must contain none.
_WRONG_RATIONALE_MARKERS = (
    "no torque observation",
    "absent torque observation",
    "torque is not observed",
    "no torque feedback",
    "tau_states",
)


def test_reason_states_the_missing_finger_dynamics_model() -> None:
    reason = GRIPPER_RESIDUAL_DISABLED_REASON.lower()
    assert "finger" in reason
    assert "model" in reason


def test_reason_states_the_constant_grasp_offset() -> None:
    reason = GRIPPER_RESIDUAL_DISABLED_REASON.lower()
    assert "constant torque offset" in reason


def test_reason_is_not_no_torque_observation() -> None:
    reason = GRIPPER_RESIDUAL_DISABLED_REASON.lower()
    for marker in _WRONG_RATIONALE_MARKERS:
        assert marker not in reason, f"reason wrongly cites {marker!r}"


def test_reason_reuses_the_single_wp2b01_fact() -> None:
    # One owner for the two facts: the reason embeds WP-2B-01's GRIPPER_MODEL_REASON.
    assert GRIPPER_MODEL_REASON in GRIPPER_RESIDUAL_DISABLED_REASON


def test_gripper_torque_is_observed() -> None:
    # The exclusion is the missing model, not missing observation — torque is observed.
    assert GRIPPER_TORQUE_IS_OBSERVED is True
    assert gripper_torque_is_observed() is True
