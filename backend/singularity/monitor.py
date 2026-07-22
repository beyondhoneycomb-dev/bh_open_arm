"""Jacobian singularity monitor: velocity damping and warning (WP-2D-02, FR-MAN-026).

mink damps a near-singular solve with Tikhonov regularisation but never tells the
operator (FR-MAN-026). This guard makes the proximity observable and acts on it: it
installs itself as the jog's WP-2D-01 singularity monitor, and before each step — when
the jog hands over the jogged side's committed arm joints — it forms the 6x7 Jacobian,
takes its smallest singular value, and turns that into a jog velocity scale on a ramp
between two settable thresholds. Above the warn value the jog runs full speed; between
warn and floor it is damped; at or below the floor the jog holds, because no finite
scale carries a jog safely through an exact degeneracy (the scale never reaches zero,
so a hold is the only honest way to stop there).

The reused jog assesses the monitor *after* applying a step's delta, so a fresh damping
takes effect on the following step — reactive damping keyed to the config the jog is
sitting at, which is the config a further jog would move away from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from backend.cartesian_jog.constants import FULL_VELOCITY_SCALE
from backend.singularity.constants import DAMPED_FLOOR_SCALE
from backend.singularity.kinematics import ArmJacobian

if TYPE_CHECKING:
    from backend.cartesian_jog import CartesianJog


@dataclass(frozen=True)
class SingularityMetrics:
    """One assessment of how close an arm is to a Jacobian singularity.

    Attributes:
        sigma_min: The smallest singular value of the 6x7 arm Jacobian; zero at an exact
            singularity, so the primary proximity measure (FR-MAN-026).
        sigma_max: The largest singular value.
        condition_number: ``sigma_max / sigma_min`` (infinite at a singularity), the
            alternative FR-MAN-026 metric.
        velocity_scale: The jog velocity scale this assessment calls for, in (0, 1].
        damping: True when the arm is near enough that the Cartesian jog is damped.
        critical: True when it is degenerate enough that the jog holds (below the floor).
    """

    sigma_min: float
    sigma_max: float
    condition_number: float
    velocity_scale: float
    damping: bool
    critical: bool


class SingularityGuard:
    """Monitors a jog for Jacobian singularities: damps and warns, holds at the floor.

    Not thread-safe: one guard serves one jog on one thread, holding the jog reference
    and the last assessment across steps. Both thresholds are settable at runtime
    (acceptance ③); the guard never mutates the jog other than through the two public
    setters ``set_velocity_scale`` and ``set_singularity_monitor`` it was given.
    """

    def __init__(
        self,
        jacobian: ArmJacobian,
        warn_sigma_min: float,
        floor_sigma_min: float,
    ) -> None:
        """Initialize; prefer ``build_singularity_guard`` which builds the Jacobian context.

        Args:
            jacobian: The FK/Jacobian context (same asset as the guarded jog).
            warn_sigma_min: sigma_min below which the jog is damped and a warning raised.
            floor_sigma_min: sigma_min at or below which the jog holds.
        """
        _validate_thresholds(warn_sigma_min, floor_sigma_min)
        self._jacobian = jacobian
        self._warn = float(warn_sigma_min)
        self._floor = float(floor_sigma_min)
        self._jog: CartesianJog | None = None
        self._last_metrics: SingularityMetrics | None = None
        self._last_warning: str | None = None

    # -- thresholds (acceptance ③) -----------------------------------------------

    @property
    def warn_sigma_min(self) -> float:
        """Return the sigma_min below which the jog is damped."""
        return self._warn

    @property
    def floor_sigma_min(self) -> float:
        """Return the sigma_min at or below which the jog holds."""
        return self._floor

    def set_warn_sigma_min(self, value: float) -> None:
        """Set the damping threshold; must stay above the floor."""
        _validate_thresholds(value, self._floor)
        self._warn = float(value)

    def set_floor_sigma_min(self, value: float) -> None:
        """Set the hold threshold; must stay below the warn threshold and above zero."""
        _validate_thresholds(self._warn, value)
        self._floor = float(value)

    # -- installation ------------------------------------------------------------

    def attach(self, jog: CartesianJog) -> None:
        """Install this guard as ``jog``'s singularity monitor and velocity-damp target."""
        self._jog = jog
        jog.set_singularity_monitor(self._on_step)

    def detach(self) -> None:
        """Uninstall the monitor and restore full jog velocity."""
        if self._jog is not None:
            self._jog.set_singularity_monitor(None)
            self._jog.set_velocity_scale(FULL_VELOCITY_SCALE)
        self._jog = None

    @property
    def last_metrics(self) -> SingularityMetrics | None:
        """Return the metrics from the most recent assessment, or None before the first."""
        return self._last_metrics

    @property
    def last_warning(self) -> str | None:
        """Return the most recent warning text, or None when the last step was clear."""
        return self._last_warning

    # -- evaluation --------------------------------------------------------------

    def evaluate(self, side: str, arm_joints: np.ndarray) -> SingularityMetrics:
        """Assess the singularity proximity of ``side`` at ``arm_joints`` (no side effects)."""
        values = self._jacobian.singular_values(side, arm_joints)
        sigma_min = float(values[-1])
        sigma_max = float(values[0])
        condition = sigma_max / sigma_min if sigma_min > 0.0 else float("inf")
        scale, damping, critical = self._ramp(sigma_min)
        return SingularityMetrics(
            sigma_min=sigma_min,
            sigma_max=sigma_max,
            condition_number=condition,
            velocity_scale=scale,
            damping=damping,
            critical=critical,
        )

    def _ramp(self, sigma_min: float) -> tuple[float, bool, bool]:
        """Map sigma_min to (velocity_scale, damping, critical) on the two-threshold ramp."""
        if sigma_min >= self._warn:
            return FULL_VELOCITY_SCALE, False, False
        if sigma_min <= self._floor:
            return DAMPED_FLOOR_SCALE, True, True
        fraction = (sigma_min - self._floor) / (self._warn - self._floor)
        scale = DAMPED_FLOOR_SCALE + fraction * (FULL_VELOCITY_SCALE - DAMPED_FLOOR_SCALE)
        return scale, True, False

    def _on_step(self, side: str, arm_joints: np.ndarray) -> str | None:
        """The jog's singularity-monitor callback: damp, remember, and hold at the floor.

        Returns the hold reason string only when the config is below the floor (the jog
        then stops with ``JogStopReason.SINGULARITY``); otherwise it damps the jog's
        velocity scale as a side effect and lets the step proceed.
        """
        metrics = self.evaluate(side, arm_joints)
        self._last_metrics = metrics
        if self._jog is not None:
            self._jog.set_velocity_scale(metrics.velocity_scale)
        if metrics.critical:
            self._last_warning = _warning_text(side, metrics)
            return self._last_warning
        self._last_warning = _warning_text(side, metrics) if metrics.damping else None
        return None


def _validate_thresholds(warn: float, floor: float) -> None:
    """Reject a threshold pair that is non-positive or not warn > floor."""
    if not floor > 0.0:
        raise ValueError(f"floor_sigma_min must be > 0, got {floor}")
    if not warn > floor:
        raise ValueError(f"warn_sigma_min ({warn}) must be greater than floor ({floor})")


def _warning_text(side: str, metrics: SingularityMetrics) -> str:
    """Build the operator warning for a damped or held step."""
    state = "holding (singularity)" if metrics.critical else "damping"
    return (
        f"{side} arm near a Jacobian singularity: sigma_min={metrics.sigma_min:.4f}, "
        f"condition={metrics.condition_number:.1f}, {state} at "
        f"velocity_scale={metrics.velocity_scale:.3f}"
    )
