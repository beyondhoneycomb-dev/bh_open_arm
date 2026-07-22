"""Shared fixtures for WP-1-03: safety-limit builders, a fake bus, and a follower factory.

The filter and gateway are exercised at a small joint width so a scenario that
triggers exactly one check is easy to read; the follower factory builds the real
`OaOpenArmFollower` over a CAN-free fake bus so the enforcement point runs with no
hardware present.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from backend.actuation import (
    ActuationGateway,
    CollisionGuard,
    ManualClock,
    SafetyFilter,
    SafetyLimits,
)
from backend.calibration.schema import MOTOR_ORDER
from contracts.plugin.config import Side
from contracts.units import Deg, Nm
from ops.cancel.scheduler import LatchReason
from packages.lerobot_robot_openarm.config_oa import OaOpenArmFollowerConfig
from packages.lerobot_robot_openarm.openarm_follower_oa import OaOpenArmFollower

# A small joint width for filter scenarios; the real arm is 8, but two joints make a
# single-check trigger readable and the filter is width-agnostic.
NARROW_WIDTH = 2

# The control period the rate checks divide by, in the tests.
TEST_DT_SEC = 0.02
TEST_FRESHNESS_SEC = 0.05


def make_limits(
    width: int = NARROW_WIDTH,
    *,
    mechanical_deg: float = 180.0,
    operational_deg: float = 90.0,
    velocity_rad_s: float = 1000.0,
    accel_rad_s2: float = 1.0e9,
    jerk_rad_s3: float = 1.0e12,
    step_delta_rad: float = 100.0,
    peak_torque_nm: float = 40.0,
    operational_torque_nm: float = 40.0,
) -> SafetyLimits:
    """Build a uniform-per-joint limit set, loose by default so one knob triggers one check.

    Args:
        width: Number of joints.
        mechanical_deg: Symmetric mechanical position bound.
        operational_deg: Symmetric operational position bound (a subset of mechanical).
        velocity_rad_s: Per-joint velocity ceiling.
        accel_rad_s2: Per-joint acceleration ceiling.
        jerk_rad_s3: Per-joint jerk ceiling.
        step_delta_rad: Per-joint step-delta jump guard.
        peak_torque_nm: Per-joint physical Peak Torque.
        operational_torque_nm: Per-joint operational torque bound.

    Returns:
        (SafetyLimits) The limit set.
    """
    return SafetyLimits(
        mechanical_deg=tuple((Deg(-mechanical_deg), Deg(mechanical_deg)) for _ in range(width)),
        operational_deg=tuple((Deg(-operational_deg), Deg(operational_deg)) for _ in range(width)),
        velocity_limit_rad_s=tuple(velocity_rad_s for _ in range(width)),
        accel_limit_rad_s2=tuple(accel_rad_s2 for _ in range(width)),
        jerk_limit_rad_s3=tuple(jerk_rad_s3 for _ in range(width)),
        step_delta_limit_rad=tuple(step_delta_rad for _ in range(width)),
        peak_torque_nm=tuple(Nm(peak_torque_nm) for _ in range(width)),
        operational_torque_nm=tuple(Nm(operational_torque_nm) for _ in range(width)),
    )


def make_gateway(
    limits: SafetyLimits,
    on_latch: Callable[[LatchReason], None] | None = None,
) -> tuple[ActuationGateway, CollisionGuard]:
    """Build a gateway over a filter and a manual-clock guard.

    Args:
        limits: The safety envelope.
        on_latch: Optional latch callback; a no-op recorder otherwise.

    Returns:
        (tuple[ActuationGateway, CollisionGuard]) The gateway and its guard.
    """
    guard = CollisionGuard(on_latch=on_latch or (lambda _reason: None), clock=ManualClock())
    gateway = ActuationGateway(
        SafetyFilter(limits),
        guard,
        dt_sec=TEST_DT_SEC,
        freshness_window_sec=TEST_FRESHNESS_SEC,
    )
    return gateway, guard


def degs(*values: float) -> tuple[Deg, ...]:
    """Build a degree tuple from raw floats."""
    return tuple(Deg(value) for value in values)


class FakeArmBus:
    """A CAN-free 8-motor bus double: readable state, no socket, no MIT write.

    It supports the LeRobot observation read path (`motors`, `sync_read_all_states`)
    and the WP-1-02 flow, but has no `_mit_control_batch` — the follower's gateway is
    the only write path, and it never reaches for one, so its absence is deliberate.
    """

    def __init__(self, position_deg: float = 0.0) -> None:
        """Build the bus reporting a fixed joint angle.

        Args:
            position_deg: The angle every motor reports on a readback.
        """
        self._position_deg = position_deg
        self.is_connected = True
        self.motors = list(MOTOR_ORDER)

    def sync_read_all_states(self) -> dict[str, dict[str, float]]:
        """Return a readback frame for every motor at the configured position."""
        return {
            motor: {"position": self._position_deg, "velocity": 0.0, "torque": 0.0}
            for motor in MOTOR_ORDER
        }

    def disconnect(self, disable_torque: bool = False) -> None:
        """Close the bus (no socket was open)."""
        self.is_connected = False


@pytest.fixture
def make_follower(tmp_path: Path) -> Callable[..., OaOpenArmFollower]:
    """Return a factory building a fixture-bus `OaOpenArmFollower` in a temp calib dir."""

    def _make(
        side: Side = Side.LEFT,
        robot_id: str = "wp103_arm",
        position_deg: float = 0.0,
    ) -> OaOpenArmFollower:
        bus = FakeArmBus(position_deg=position_deg)
        config = OaOpenArmFollowerConfig(side=side, id=robot_id, calibration_dir=tmp_path)
        return OaOpenArmFollower(config, bus=bus)

    return _make
