"""Reuse invariants — the zero record and its vocabulary come from one source.

The audit hunts for two sources of truth. WP-2D-05 adds the postures that depend on
the zero record and the gate over them; it reuses ``backend.calibration`` for the zero
vocabulary and shape, and ties its joint width to the calibration motor count, so a
teaching point can never disagree with the record it is gated against.
"""

from __future__ import annotations

import backend.teaching.point as point_module
import backend.teaching.zero_match as zero_match_module
from backend.calibration import MOTOR_COUNT, ZeroMethod
from backend.teaching import Q_URDF_WIDTH, ZeroIdentity

from . import RIGHT, make_calibration


def test_zero_method_enum_is_the_calibration_one_not_a_second_copy() -> None:
    assert point_module.ZeroMethod is ZeroMethod
    assert zero_match_module.ZeroMethod is ZeroMethod


def test_joint_width_is_bound_to_the_calibration_motor_count() -> None:
    assert Q_URDF_WIDTH == MOTOR_COUNT


def test_zero_identity_is_derived_from_the_frozen_calibration_record() -> None:
    calibration = make_calibration(RIGHT)
    derived = ZeroIdentity.from_calibration(calibration)
    assert derived.side == calibration.side
    assert derived.zero_method is calibration.zero_method
    assert derived.zeroed_at == calibration.last_zero_at


def test_persistence_does_not_reimport_the_calibration_writer() -> None:
    # The atomic discipline is reused; the schema-bound calibration writer is not, since
    # it only persists an OpenArmCalibration. Guard against a future edit quietly wiring
    # the collection through the wrong, payload-typed writer.
    import backend.teaching.persistence as persistence_module

    source = persistence_module.__doc__ or ""
    assert "persist-then-swap" in source
    assert not hasattr(persistence_module, "save_calibration_atomic")
