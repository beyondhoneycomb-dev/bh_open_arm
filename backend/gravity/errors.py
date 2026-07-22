"""The single error type the WP-2B-02 gravity backend raises on a refused build or evaluation.

A subclass of `ValueError` so a caller already guarding config loads for `ValueError` keeps
working, while a caller that wants to tell a gravity-backend refusal apart from an unrelated
value error can catch this type specifically.
"""

from __future__ import annotations


class GravityBackendError(ValueError):
    """A gravity backend that cannot be built or evaluated as configured.

    Raised for a model that fails the v2-convention cross-check (a mis-versioned or non-v2
    MJCF — guarded because a v1-convention model yields a plausible-looking but wrong shoulder
    gravity term, spec 12 §2.6), a joint vector of the wrong width, a `gravity_scale` outside
    `[0, 1.2]`, or an unknown joint name. The build or call is refused at the point of use
    rather than returning a silently wrong torque.
    """
