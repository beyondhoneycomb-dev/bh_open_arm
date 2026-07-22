"""WP-2B-08 — the path-B bootstrap: v2 gravity+Coriolis, friction uncompensated, detection locked.

Path B is the conditional fallback 02b §2.1 spins up when PG-FRIC-001 takes its negative branch
(the v2 friction model could not be identified). It brings the gravity term back to life for the
twin and dry-run without pretending friction is compensated:

* Gravity+Coriolis come from the committed v2 MJCF's `qfrc_bias`, reused through WP-2B-02's
  `MuJoCoV2GravityBackend` rather than recomputed here. WP-2B-02 froze `tau_grav(q)` as the single
  gravity compute point (FR-SAF-034); a second qfrc_bias reimplementation would break that
  invariant, so path B composes the existing backend. The bias excludes MJCF `frictionloss` by
  construction, which is exactly why friction stays uncompensated and the low-speed tanh
  static-friction knee is unreproduced (spec 12 §2.6 path B).
* The banner is always shown and collision detection is locked DISABLED — the two defenses
  FR-SAF-030 requires while the model is unidentified.
* PG-FRIC-001's outcome is FAIL_BLOCKING and cannot be recorded otherwise: 02b §2.1 forbids
  recording path B as a "partial success".

Ownership/threading: owns one `MuJoCoV2GravityBackend`, which owns a private mujoco scratch buffer
mutated on every call, so one `PathBBootstrap` is used from one thread.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.gravity import Arm, MuJoCoV2GravityBackend
from backend.pathb.banner import PathBBanner
from backend.pathb.constants import PG_FRIC_OUTCOME
from backend.pathb.detection_lock import DetectionLock
from backend.pathb.errors import PathBError


class PathBBootstrap:
    """Gravity+Coriolis bootstrap for one arm, with the banner and detection lock path B mandates.

    Input convention is WP-2B-02's: joint angles are the arm's seven values in the v2 joint
    convention (radians). Width and convention are validated by the reused backend, so a
    wrong-width vector raises `GravityBackendError` (a `ValueError`) at the compute point.
    """

    def __init__(self, arm: Arm = Arm.RIGHT) -> None:
        """Build the bootstrap: load the v2 gravity backend for `arm`, arm the banner and lock.

        The gravity backend is built at its default gravity_scale (1.0 = full v2-inertia model):
        path B is a faithful bootstrap of the model, not a trim point. Compensation-scale
        separation is WP-2B-09's concern and is kept out of the fallback.

        Args:
            arm: The follower arm to compute for; the right arm is the WP-2B-01 reference arm.
        """
        self._backend = MuJoCoV2GravityBackend(arm)
        self._banner = PathBBanner()
        self._detection = DetectionLock()

    @property
    def arm(self) -> Arm:
        """The arm this bootstrap computes for."""
        return self._backend.arm

    @property
    def banner(self) -> PathBBanner:
        """The always-shown friction-uncompensated banner (CG-2B-08b)."""
        return self._banner

    @property
    def detection(self) -> DetectionLock:
        """The detection-enable lock, held DISABLED (CG-2B-08c, FR-SAF-030)."""
        return self._detection

    @property
    def pg_fric_outcome(self) -> str:
        """Path B's only PG-FRIC-001 outcome: FAIL_BLOCKING (02b §2.1). Read-only by design."""
        return PG_FRIC_OUTCOME

    def gravity_coriolis(self, q: Sequence[float], qdot: Sequence[float]) -> tuple[float, ...]:
        """Return gravity+Coriolis `C(q, q̇)·q̇ + g(q)` from the v2 MJCF bias — no friction term.

        The qfrc_bias reused from WP-2B-02 excludes MJCF frictionloss, so this is gravity and
        Coriolis only, which is the path-B contract (02b §2.3): the low-speed tanh friction knee
        is not present, hence detection stays locked.

        Args:
            q: One arm's seven joint angles, v2 convention, radians.
            qdot: One arm's seven joint velocities, rad/s.

        Returns:
            (tuple[float, ...]) Per-joint gravity+Coriolis torque in Nm, joint1..joint7 order.

        Raises:
            GravityBackendError: On a joint vector of the wrong width.
        """
        return self._backend.tau_bias(q, qdot)

    def gravity(self, q: Sequence[float]) -> tuple[float, ...]:
        """Return the gravity torque `g(q)` at zero velocity (the static twin/dry-run term).

        Args:
            q: One arm's seven joint angles, v2 convention, radians.

        Returns:
            (tuple[float, ...]) Per-joint gravity torque in Nm, joint1..joint7 order.

        Raises:
            GravityBackendError: On a joint vector of the wrong width.
        """
        return self._backend.tau_grav(q)

    def record_outcome(self, outcome: str) -> str:
        """Validate a PG-FRIC-001 outcome for path B, accepting only FAIL_BLOCKING.

        The 02b §2.1 negative branch: recording path B as a "partial success" — or any PASS /
        DEGRADED_ACCEPTED — is itself the FAIL_BLOCKING defect. This is the reporting boundary that
        refuses it in code rather than trusting the caller to record it honestly.

        Args:
            outcome: The PG-FRIC-001 outcome a caller intends to record.

        Returns:
            (str) `FAIL_BLOCKING`, the only permitted outcome.

        Raises:
            PathBError: If `outcome` is anything other than FAIL_BLOCKING.
        """
        if outcome != PG_FRIC_OUTCOME:
            raise PathBError(
                f"path B may only record PG-FRIC-001 as {PG_FRIC_OUTCOME!r}, not {outcome!r}: "
                "recording path B as a partial success is the FAIL_BLOCKING defect (02b §2.1)"
            )
        return PG_FRIC_OUTCOME
