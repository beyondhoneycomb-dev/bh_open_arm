"""The friction feed-forward `F_hat(q_dot)` — the observer's friction term, reused not re-fit.

WP-2C-01 consumes WP-2B-07's identified friction; it does not re-identify anything. This wraps a
per-joint tuple of `backend.friction.FrictionParams` and evaluates the four-term tanh law at the
current joint velocities. Offline (this host, no PG-FRIC-001 pass) the natural source is the v1
seed `backend.friction.V1_SEED_FRICTION` — the only friction that exists until the real fit lands
— and a real run swaps in the identified `friction.yaml` parameters through the same interface.

The observer models detection at full friction (100%), independent of the reduced control-side
compensation scale (WP-2B-09); this term is that full-friction model, so no scale is applied here.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from backend.friction.active import ActiveFrictionProfile, v1_seed_profile
from backend.gmo.constants import GMO_JOINT_COUNT
from backend.gmo.errors import GmoJointCountError


class FrictionFeedforward:
    """Per-joint friction torque `F_hat(q_dot)` from identified (or seed) friction parameters.

    Takes a profile rather than bare parameters so that the friction the observer is subtracting
    can always name which robot it describes (NORM-012). An anonymous parameter set would make
    `profile.is_reidentified` unanswerable at exactly the moment it matters — a residual that
    looks wrong and no way to tell whether the friction model is the reason.
    """

    def __init__(self, profile: ActiveFrictionProfile | None = None) -> None:
        """Store the friction profile, refusing a parameter set of the wrong width.

        Args:
            profile: The friction in use, or None for the v1 seed — the offline stand-in until
                WP-2B-07's identified parameters are available.

        Raises:
            GmoJointCountError: If the profile does not hold `GMO_JOINT_COUNT` parameter sets.
        """
        active = profile if profile is not None else v1_seed_profile()
        if len(active.params) != GMO_JOINT_COUNT:
            raise GmoJointCountError(
                f"friction params must have {GMO_JOINT_COUNT} entries, got {len(active.params)}"
            )
        self._profile = active
        self._params = active.params

    @property
    def profile(self) -> ActiveFrictionProfile:
        """The friction profile being subtracted, with the stamp saying which robot it describes."""
        return self._profile

    def friction(self, qdot: Sequence[float]) -> NDArray[np.float64]:
        """Return the per-joint friction torque at the joint velocities `qdot`.

        Args:
            qdot: One arm's seven joint velocities, rad/s.

        Returns:
            (NDArray[np.float64]) Per-joint friction torque `F_hat`, Nm, joint1..joint7 order.

        Raises:
            GmoJointCountError: On a velocity vector of the wrong width.
        """
        rates = np.asarray(qdot, dtype=np.float64)
        if rates.shape != (GMO_JOINT_COUNT,):
            raise GmoJointCountError(
                f"velocity vector must have {GMO_JOINT_COUNT} entries, got shape {rates.shape}"
            )
        return np.array(
            [
                float(param.tau(np.array([rate]))[0])
                for param, rate in zip(self._params, rates, strict=True)
            ],
            dtype=np.float64,
        )
