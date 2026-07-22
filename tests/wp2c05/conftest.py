"""Shared fixtures for the WP-2C-05 reaction-strategy acceptances.

A neutral bimanual reaction context (16 joints, matching the MIT batch width the
scheduler and fake CAN writer expect) and the two channel capabilities the guards key
on. The context is a well-formed stand-in, not a physical claim: `q_hold` is a rest
pose and `tau_grav` a nonzero gravity term so a dropped `τ_grav` is observable.
"""

from __future__ import annotations

import pytest

from backend.actuation import MIT_BATCH_WIDTH
from backend.reaction import ReactionContext, TorqueChannel
from contracts.units import Nm, Rad


@pytest.fixture
def width() -> int:
    """The bimanual MIT batch width the scheduler and writer use."""
    return MIT_BATCH_WIDTH


@pytest.fixture
def context(width: int) -> ReactionContext:
    """A neutral 16-joint reaction context with nonzero gains and gravity term."""
    return ReactionContext(
        kp_orig=tuple(40.0 for _ in range(width)),
        kd_orig=tuple(1.0 for _ in range(width)),
        q_hold=tuple(Rad(0.05 * index) for index in range(width)),
        tau_grav=tuple(Nm(0.3) for _ in range(width)),
        residual=(1.0,) + tuple(0.0 for _ in range(width - 1)),
    )


@pytest.fixture
def channel_available() -> TorqueChannel:
    """The FR-SAF-069 extension present: both feed-forward channels reach the bus."""
    return TorqueChannel.available()


@pytest.fixture
def channel_unavailable() -> TorqueChannel:
    """The stock path: no feed-forward channel (tau/vel hardcoded to zero)."""
    return TorqueChannel.unavailable()
