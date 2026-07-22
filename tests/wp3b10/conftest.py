"""Shared builders for the WP-3B-10 teleop safety-gate tests.

The gate is driven against the frozen `CTR-TEL@v1` sample and a controllable lease
view, both real inputs: `make_sample` builds a genuine `TeleopSample`, and
`FakeLease` is the minimal `LeaseLatchView` the gate depends on (a togglable latch),
used where a deterministic latch state is wanted. The lease-latch integration test
(`test_lease_latch_gate.py`) instead drives the *real* `DeadmanController`, so the
"lease is superior" claim is proven against the object the deadman actually owns.

All times are server-clock nanoseconds, matching the gate's `now_ns` and the
`TeleopSample.receive_mono_ns` domain.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.teleop.safety_gate import (
    EEPose,
    EEVelocityLimiter,
    LeaseLatchView,
    LinkHeartbeat,
    PoseSanityFilter,
    TeleopSafetyGate,
    WorkspaceBox,
)
from backend.teleop.safety_gate.pose import IDENTITY_ROTATION, Matrix3, Vector3
from contracts.teleop import TeleopSample, TeleopValidity

# 10 ms control period, in nanoseconds — well under the 100 ms heartbeat timeout, so a
# fresh sample each tick keeps the link live and a chosen number of dropped ticks
# crosses the timeout deterministically.
TICK_NS = 10_000_000
DT_SEC = 0.01
NANOS_PER_SECOND = 1_000_000_000

# A workspace box wide enough that ordinary following never touches it; the wall tests
# pick targets deliberately outside it.
WIDE_BOX = WorkspaceBox(min_corner=(-2.0, -2.0, -2.0), max_corner=(2.0, 2.0, 2.0))


def rotation_z(theta: float) -> Matrix3:
    """Return the rotation matrix of `theta` radians about the base z-axis."""
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    return ((cos_t, -sin_t, 0.0), (sin_t, cos_t, 0.0), (0.0, 0.0, 1.0))


def pose_at(translation: Vector3, rotation: Matrix3 = IDENTITY_ROTATION) -> EEPose:
    """Build an `EEPose` at a translation with an optional rotation (identity default)."""
    return EEPose(rotation=rotation, translation=translation)


def make_sample(
    receive_mono_ns: int,
    validity: TeleopValidity = TeleopValidity.OK,
    source_ts: float = 0.0,
) -> TeleopSample:
    """Build a real `CTR-TEL@v1` sample at a server-clock receive instant."""
    return TeleopSample(source_ts=source_ts, receive_mono_ns=receive_mono_ns, validity=validity)


@dataclass
class FakeLease:
    """A minimal `LeaseLatchView` with a togglable latch, for deterministic gate tests.

    Attributes:
        latched: Whether the (stand-in) deadman lease latch is engaged.
    """

    latched: bool = False


def make_gate(
    seed_pose: EEPose,
    lease: LeaseLatchView | None = None,
    box: WorkspaceBox = WIDE_BOX,
    max_linear_vel_m_s: float = 100.0,
    max_angular_vel_rad_s: float = 100.0,
    decel_m_s2: float = 4.0,
) -> TeleopSafetyGate:
    """Assemble a gate over real filters, defaulting the velocity limit non-binding.

    The velocity ceilings default high so a test isolating another stage (workspace,
    sanity, decel) is not perturbed by clamping; the velocity tests lower them.

    Args:
        seed_pose: The measured EE pose at engage.
        lease: The lease latch view; a fresh unlatched `FakeLease` by default.
        box: The workspace box; the wide box by default.
        max_linear_vel_m_s: Linear velocity ceiling.
        max_angular_vel_rad_s: Angular velocity ceiling.
        decel_m_s2: Link-loss deceleration.

    Returns:
        (TeleopSafetyGate) The composed gate, in its initial ALIGNING state.
    """
    return TeleopSafetyGate(
        dt_sec=DT_SEC,
        heartbeat=LinkHeartbeat(),
        workspace=box,
        velocity_limiter=EEVelocityLimiter(
            dt_sec=DT_SEC,
            max_linear_vel_m_s=max_linear_vel_m_s,
            max_angular_vel_rad_s=max_angular_vel_rad_s,
        ),
        sanity=PoseSanityFilter(),
        lease=lease if lease is not None else FakeLease(),
        seed_pose=seed_pose,
        decel_m_s2=decel_m_s2,
    )
