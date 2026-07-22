"""The frozen gravity-backend contract: `tau_grav(q)` is the single gravity compute point.

FR-SAF-034 / spec 12 §2.6 name two backends — `MUJOCO_V2` (default, v2 inertia) and
`URDF_KDL` (the legacy `Dynamics::GetGravity` family) — behind one interface. This module owns
that interface and the runtime `gravity_scale` knob; the concrete backends live in
`mujoco_v2` and `urdf_kdl`, and `selector.select_backend` chooses between them.

Contract note carried for downstream consumers (WP-2B-07 friction fit, WP-2C-01 GMO): the
gravity term has exactly one source, this backend. `openarm_control` carries no dynamics model
(spec 12 §2.6: "kinematics/config/poses 3개 파일뿐"), so nothing downstream may assume force
control is available from it — the torque path it needs is FR-SAF-069, not this package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import Enum

from backend.gravity.constants import GRAVITY_SCALE_MAX, GRAVITY_SCALE_MIN
from backend.gravity.errors import GravityBackendError


class Arm(Enum):
    """Which follower arm a backend computes for. The right arm is the WP-2B-01 reference arm."""

    RIGHT = "right"
    LEFT = "left"


class BackendId(Enum):
    """The dynamics backend selector value (FR-SAF-034, spec 12 §2.6 `comp.dynamics_backend`)."""

    MUJOCO_V2 = "MUJOCO_V2"
    URDF_KDL = "URDF_KDL"


class GravityBackend(ABC):
    """A single-arm gravity-torque computer with a runtime gravity trim.

    Ownership/threading: a concrete backend owns a private mujoco scratch buffer that it
    mutates on every call, so one backend instance is used from one thread — the actuation or
    identification loop that calls it. Share nothing across threads; build one per consumer.
    """

    def __init__(self, arm: Arm, gravity_scale: float) -> None:
        """Store the arm and validate the initial gravity scale via the property setter."""
        self._arm = arm
        self._gravity_scale = GRAVITY_SCALE_MIN
        self.gravity_scale = gravity_scale

    @property
    def arm(self) -> Arm:
        """The arm this backend computes for."""
        return self._arm

    @property
    @abstractmethod
    def backend_id(self) -> BackendId:
        """The backend's selector value (FR-SAF-034)."""

    @property
    def gravity_scale(self) -> float:
        """The runtime gravity trim in `[0, 1.2]` (default 1.0 = full modelled gravity)."""
        return self._gravity_scale

    @gravity_scale.setter
    def gravity_scale(self, value: float) -> None:
        """Set the gravity trim, refusing any value outside `[0, 1.2]`.

        Raises:
            GravityBackendError: If `value` is outside the runtime band. A payload/gravity
                trim outside range is a misconfiguration, refused rather than silently clamped.
        """
        scale = float(value)
        if not GRAVITY_SCALE_MIN <= scale <= GRAVITY_SCALE_MAX:
            raise GravityBackendError(
                f"gravity_scale must be in [{GRAVITY_SCALE_MIN}, {GRAVITY_SCALE_MAX}], got {scale}"
            )
        self._gravity_scale = scale

    @abstractmethod
    def tau_grav(self, q: Sequence[float]) -> tuple[float, ...]:
        """Return the gravity generalized torque for the arm's seven joints at zero velocity.

        The single gravity compute point. `q` is one arm's joint angles in the v2 convention,
        radians; the result is scaled by `gravity_scale` and is the term WP-2B-07 subtracts as
        the gravity contribution and WP-2C-01 uses as `ĝ(q)`.

        Args:
            q: One arm's seven joint angles, v2 convention, radians.

        Returns:
            (tuple[float, ...]) Per-joint gravity torque in Nm, joint1..joint7 order.

        Raises:
            GravityBackendError: On a joint vector of the wrong width.
        """
