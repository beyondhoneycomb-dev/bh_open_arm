"""The `endEffector` subobject converts to a `RigEndEffectors`, and what that decides.

`motor_send_ids` is the polling truth. These assertions are about which CAN ids a stored
configuration puts on the bus, because that is the whole reason the subobject is refused rather
than defaulted: a frame addressed to a motor that is not there is never ACKed, the transmit
error counter climbs, and the controller drops to `ERROR-PASSIVE`, degrading the seven joints
that are present.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.config.constants import FIELD_TOOL_ID, FIELD_TOOL_MASS_KG
from backend.config.model import EndEffectorConfig, default_document, rig_from_document
from backend.endeffector import (
    ARM_JOINT_SEND_IDS,
    DEFAULT_TOOL_ID,
    GRIPPER_SEND_ID,
    SIDE_LEFT,
    SIDE_RIGHT,
    TOOL_GRIPPER,
    EndEffectorError,
    RigEndEffectors,
)
from tests.wpg00_backend.conftest import GRIPPER_ON_BOTH_ARMS

MEASURED_MASS_KG = 0.42
SPATULA_MOTOR_COUNT = len(ARM_JOINT_SEND_IDS)
GRIPPER_MOTOR_COUNT = SPATULA_MOTOR_COUNT + 1


def test_default_document_polls_nothing_on_the_gripper_id() -> None:
    """The default answer under-polls: `0x08` is absent from both arms."""
    rig = rig_from_document(default_document())

    assert isinstance(rig, RigEndEffectors)
    assert GRIPPER_SEND_ID not in rig.left.motor_send_ids
    assert GRIPPER_SEND_ID not in rig.right.motor_send_ids
    assert rig.total_motor_count == 2 * SPATULA_MOTOR_COUNT


def test_a_stored_gripper_puts_the_motor_on_the_bus() -> None:
    """The stored answer is what decides the polled id set, per arm."""
    rig = EndEffectorConfig.model_validate(GRIPPER_ON_BOTH_ARMS).to_rig()

    assert GRIPPER_SEND_ID in rig.left.motor_send_ids
    assert rig.left.motor_count == GRIPPER_MOTOR_COUNT
    assert rig.right.motor_count == GRIPPER_MOTOR_COUNT


def test_the_two_arms_are_configured_independently() -> None:
    """One arm's tool says nothing about the other's — the operator chooses per arm."""
    rig = EndEffectorConfig.model_validate(
        {
            SIDE_LEFT: {FIELD_TOOL_ID: TOOL_GRIPPER, FIELD_TOOL_MASS_KG: None},
            SIDE_RIGHT: {FIELD_TOOL_ID: DEFAULT_TOOL_ID, FIELD_TOOL_MASS_KG: None},
        }
    ).to_rig()

    assert GRIPPER_SEND_ID in rig.left.motor_send_ids
    assert GRIPPER_SEND_ID not in rig.right.motor_send_ids


def test_a_convertible_config_is_the_only_config_that_exists() -> None:
    """The conversion cannot fail, because an unregistered id never becomes a config."""
    with pytest.raises(ValidationError):
        EndEffectorConfig.model_validate({SIDE_LEFT: {FIELD_TOOL_ID: "vacuum_cup"}})


def test_unmeasured_mass_reaches_the_profile_as_none() -> None:
    """Null travels as null; only `payload_mass_kg()` refuses it, and only where it is needed."""
    rig = EndEffectorConfig.model_validate(GRIPPER_ON_BOTH_ARMS).to_rig()

    assert rig.left.mass_is_measured is False
    with pytest.raises(EndEffectorError):
        rig.left.payload_mass_kg()


def test_measured_mass_reaches_payload_registration() -> None:
    """A weighed tool arrives as the number that was stored."""
    rig = EndEffectorConfig.model_validate(
        {
            SIDE_LEFT: {FIELD_TOOL_ID: TOOL_GRIPPER, FIELD_TOOL_MASS_KG: MEASURED_MASS_KG},
            SIDE_RIGHT: {FIELD_TOOL_ID: DEFAULT_TOOL_ID, FIELD_TOOL_MASS_KG: None},
        }
    ).to_rig()

    assert rig.left.payload_mass_kg() == MEASURED_MASS_KG


def test_a_no_gripper_arm_refuses_a_gripper_command() -> None:
    """What the default costs, stated: one refused command, not a degraded bus."""
    rig = rig_from_document(default_document())

    with pytest.raises(EndEffectorError):
        rig.left.assert_gripper_command_allowed(1.0)
