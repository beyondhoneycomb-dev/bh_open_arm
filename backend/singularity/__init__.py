"""Singularity monitor + elbow nullspace (WP-2D-02) over the reused WP-2D-01 jog.

Two capabilities the manual-motion band needs on top of the Cartesian jog, both built
from one 6x7 arm Jacobian and neither a second IK:

- ``SingularityGuard`` (FR-MAN-026): watches the jog's committed configuration, damps
  the Cartesian velocity on a settable ramp as the Jacobian's smallest singular value
  falls, warns, and holds at a floor.
- ``ElbowSwivel`` (FR-MAN-024): swivels the elbow through the Jacobian nullspace while
  the *reused* jog IK re-fixes the EE, so the EE pose stays fixed (verified by FK).

The Jacobian truth is ``ArmJacobian``, an FK-only reader of the same asset ``sim.ik``
resolves. The factories wire a guard or swivel to an existing jog; pass the same ``xml``
the jog was built with (None matches a default-built jog) so both read one asset.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.singularity.constants import (
    DEFAULT_FLOOR_SIGMA_MIN,
    DEFAULT_WARN_SIGMA_MIN,
)
from backend.singularity.kinematics import ArmJacobian
from backend.singularity.monitor import SingularityGuard, SingularityMetrics
from backend.singularity.nullspace import ElbowSwivel, SwivelResult

if TYPE_CHECKING:
    from backend.cartesian_jog import CartesianJog

__all__ = [
    "ArmJacobian",
    "ElbowSwivel",
    "SingularityGuard",
    "SingularityMetrics",
    "SwivelResult",
    "build_elbow_swivel",
    "build_singularity_guard",
]


def build_singularity_guard(
    jog: CartesianJog | None = None,
    xml: str | None = None,
    warn_sigma_min: float = DEFAULT_WARN_SIGMA_MIN,
    floor_sigma_min: float = DEFAULT_FLOOR_SIGMA_MIN,
) -> SingularityGuard:
    """Build a singularity guard, attaching it to ``jog`` when one is given.

    Args:
        jog: The jog to guard; when given, the guard installs itself as its monitor.
        xml: MJCF path for the Jacobian context; None uses the fixed cell asset (matching
            a default-built jog). Pass the same ``xml`` the jog was built with.
        warn_sigma_min: sigma_min below which the jog is damped and a warning raised.
        floor_sigma_min: sigma_min at or below which the jog holds.

    Returns:
        (SingularityGuard) A guard, attached to ``jog`` when one was passed.
    """
    guard = SingularityGuard(ArmJacobian(xml=xml), warn_sigma_min, floor_sigma_min)
    if jog is not None:
        guard.attach(jog)
    return guard


def build_elbow_swivel(jog: CartesianJog, xml: str | None = None) -> ElbowSwivel:
    """Build an elbow swivel over ``jog``.

    Args:
        jog: The WP-2D-01 Cartesian jog whose elbow is swiveled (its IK re-fixes the EE).
        xml: MJCF path for the Jacobian context; None uses the fixed cell asset. Pass the
            same ``xml`` the jog was built with so both read one asset.

    Returns:
        (ElbowSwivel) A swivel bound to ``jog``.
    """
    return ElbowSwivel(jog, ArmJacobian(xml=xml))
