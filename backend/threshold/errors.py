"""The error types the WP-2C-04 threshold package raises.

All derive from `ThresholdError` (a `ValueError`) so a caller already guarding a config load for
`ValueError` keeps working, while the two subclasses let a caller separate a malformed
configuration from the distinct, recoverable "acceleration limits are off" refusal — the latter is
a RETRY_WITH_VARIANT branch (activate the limits first, spec 12 §3.2 WP-2C-04), not a broken value.
"""

from __future__ import annotations


class ThresholdError(ValueError):
    """Base for every refusal raised by the threshold-mode / confirm-hysteresis package."""


class ThresholdConfigError(ThresholdError):
    """A threshold configuration that cannot be used as given.

    Raised for a per-joint array of the wrong width, a coefficient / ratio / sample count outside
    its spec range, or a consumed WP-2C-03 threshold outside the [10 x LSB, effort] band. The set
    is refused at construction rather than silently clamped, so a mis-specified threshold can never
    reach the residual comparison.
    """


class AccelerationLimitError(ThresholdError):
    """Detection activation attempted while joint acceleration limits are disabled.

    v2.0 `joint_limits.yaml` ships every joint with `has_acceleration_limits: false` and
    `max_acceleration: 0.0`, so unbounded acceleration lets the inertial term M(q).qddot leak into
    the residual and dominate false positives (FR-SAF-014, spec 12 §2.13). Raised only under the
    REFUSE policy; the negative branch is RETRY_WITH_VARIANT — activate the acceleration limits,
    then arm detection.
    """
