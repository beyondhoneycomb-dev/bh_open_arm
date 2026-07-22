"""Per-unit force cap: `torque_pu in [0, 1]`, physical-force intrusions refused.

Grip force is exposed per-unit only. A value outside [0, 1] is a physical-force-unit
intrusion — the per-unit-to-force conversion is undetermined and no load cell is used —
so it is refused (FR-MAN-016, FR-SAF-024b). That refusal is the "load-cell force
calibration attempt is out of range" negative branch.
"""

from __future__ import annotations

import pytest

from backend.gripper_endpoint.errors import GripperConfigError
from backend.gripper_endpoint.posforce import validate_torque_pu
from tests.wp2a08.conftest import make_record


def test_in_range_force_is_accepted() -> None:
    """A per-unit value inside [0, 1] passes through unchanged."""
    assert validate_torque_pu(0.0) == 0.0
    assert validate_torque_pu(1.0) == 1.0
    assert validate_torque_pu(0.4) == 0.4


def test_force_above_one_is_refused_as_out_of_range() -> None:
    """A force above 1 (e.g. a stray physical-unit value like 50) is out of range."""
    with pytest.raises(GripperConfigError, match="per-unit"):
        validate_torque_pu(50.0)


def test_negative_force_is_refused() -> None:
    """A negative per-unit force is out of the [0, 1] domain and refused."""
    with pytest.raises(GripperConfigError, match="per-unit"):
        validate_torque_pu(-0.1)


def test_record_refuses_out_of_range_force() -> None:
    """A record built with an out-of-range force cap is refused at construction."""
    with pytest.raises(GripperConfigError, match="per-unit"):
        make_record(torque_pu=1.5)
