"""The jnt_range override and its order contract (09 FR-SIM-080).

FR-SIM-080 is an *ordering* requirement, and the order is load-bearing rather than
stylistic: ``mink.ConfigurationLimit`` snapshots ``model.jnt_range`` into its bound
arrays at construction (configuration_limit.py) — and ``Kinematics`` builds that
limit the moment it is constructed (kinematics.py:168). So a jnt_range write that
lands *after* ``Kinematics`` is a write onto a snapshot no one reads: the limit is
already frozen from the un-overridden MJCF ranges, and "the requirement is void" is
literal, not rhetorical. The contract is therefore:

    ArmSetup created  →  overwrite jnt_range  →  Kinematics()

``OrderedIkBuild`` is the runtime half of enforcing it — a three-state machine that
refuses to build ``Kinematics`` before the override and refuses to override after
``Kinematics`` (a write that would silently do nothing). The static half — that no
one constructs ``Kinematics`` off this path at all — lives in ``sim.ik.staticcheck``.

The override also carries the second FR-SIM-080 clause: the values written must
equal LeRobot's ``joint_limits``, and a mismatch is a launch-time reject
(``LimitMismatchError``), because a model whose IK limits disagree with the clamp
applied to IK's output has two different limits and no single truth.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum, auto

import mujoco
from openarm_control.config import ArmSetup
from openarm_control.kinematics import IKParams, Kinematics

from sim.ik.limits import JointLimit

# jnt_range equality tolerance. The override writes the exact radian floats the
# limits carry, so a real match is bit-exact; the tolerance only absorbs the
# round-trip through MuJoCo's float64 storage, never a genuine limit difference.
RANGE_MATCH_TOLERANCE = 1e-9


class IkOrderError(RuntimeError):
    """Raised when the ArmSetup → override → Kinematics order is violated.

    Either a ``Kinematics`` build was requested before the jnt_range override, or an
    override was requested after ``Kinematics`` was built (where it would write onto
    a limit snapshot no one reads) — both void FR-SIM-080.
    """


class LimitMismatchError(RuntimeError):
    """Raised when post-override jnt_range does not equal the LeRobot limits.

    FR-SIM-080: the overwritten limits must match LeRobot ``joint_limits``; a
    mismatch is a launch-time reject, never a warning.
    """


class BuildStage(Enum):
    """The stages of the FR-SIM-080 build order, in the only legal sequence."""

    SETUP_CREATED = auto()
    RANGE_OVERRIDDEN = auto()
    KINEMATICS_BUILT = auto()


def _joint_id(model: mujoco.MjModel, joint_name: str) -> int:
    """Resolve a joint name to its id, rejecting an unknown name.

    Args:
        model: The MuJoCo model.
        joint_name: Fully-qualified MJCF joint name.

    Returns:
        (int) The joint id.

    Raises:
        ValueError: When the joint is absent from the model.
    """
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
    if jid < 0:
        raise ValueError(f"joint {joint_name!r} not found in model")
    return jid


def overwrite_jnt_range(setup: ArmSetup, limits: Sequence[JointLimit]) -> tuple[int, ...]:
    """Write LeRobot soft limits (radians) onto the model's jnt_range in place.

    This is the FR-SIM-080 override. It must run after ``ArmSetup`` is built and
    before any ``Kinematics``; callers should reach it through ``OrderedIkBuild``,
    which enforces that order.

    Args:
        setup: The freshly built ArmSetup whose model is overwritten.
        limits: The LeRobot soft limits to write, each carrying its radian bounds.

    Returns:
        (tuple[int, ...]) The joint ids written, in ``limits`` order.
    """
    written: list[int] = []
    for limit in limits:
        jid = _joint_id(setup.model, limit.mjcf_joint)
        setup.model.jnt_range[jid][0] = limit.lower_rad.value
        setup.model.jnt_range[jid][1] = limit.upper_rad.value
        setup.model.jnt_limited[jid] = 1
        written.append(jid)
    return tuple(written)


def verify_ranges_match(
    setup: ArmSetup,
    limits: Sequence[JointLimit],
    tolerance: float = RANGE_MATCH_TOLERANCE,
) -> None:
    """Assert every overwritten jnt_range equals its LeRobot limit, or reject.

    FR-SIM-080's second clause: post-override jnt_range must match LeRobot
    ``joint_limits``. This re-reads the model — it does not trust that the write
    happened — so a corrupted or partial override is caught at launch.

    Args:
        setup: The model to read back.
        limits: The LeRobot limits the model must now equal.
        tolerance: Absolute radian tolerance for the comparison.

    Raises:
        LimitMismatchError: When any joint's range differs from its limit.
    """
    mismatches: list[str] = []
    for limit in limits:
        jid = _joint_id(setup.model, limit.mjcf_joint)
        actual_lo = float(setup.model.jnt_range[jid][0])
        actual_hi = float(setup.model.jnt_range[jid][1])
        if (
            abs(actual_lo - limit.lower_rad.value) > tolerance
            or abs(actual_hi - limit.upper_rad.value) > tolerance
        ):
            mismatches.append(
                f"{limit.mjcf_joint}: model [{actual_lo:.6f}, {actual_hi:.6f}] rad != "
                f"LeRobot [{limit.lower_rad.value:.6f}, {limit.upper_rad.value:.6f}] rad"
            )
    if mismatches:
        raise LimitMismatchError(
            "post-override jnt_range does not match LeRobot joint_limits "
            f"({len(mismatches)} joint(s)): " + "; ".join(mismatches)
        )


class OrderedIkBuild:
    """State machine enforcing the FR-SIM-080 build order at runtime.

    One instance drives one ArmSetup from creation through the override to a single
    ``Kinematics``. It owns the setup only for the duration of the build; the
    resulting ``Kinematics`` is what the caller keeps. The machine advances in one
    direction — ``SETUP_CREATED → RANGE_OVERRIDDEN → KINEMATICS_BUILT`` — and every
    off-sequence transition raises ``IkOrderError`` rather than silently proceeding.
    """

    def __init__(self, setup: ArmSetup) -> None:
        """Begin a build at the SETUP_CREATED stage.

        Args:
            setup: The freshly built ArmSetup, before any override or Kinematics.
        """
        self._setup = setup
        self._stage = BuildStage.SETUP_CREATED
        self._limits: tuple[JointLimit, ...] = ()

    @property
    def stage(self) -> BuildStage:
        """Return the current build stage."""
        return self._stage

    @property
    def setup(self) -> ArmSetup:
        """Return the ArmSetup under construction."""
        return self._setup

    @property
    def limits(self) -> tuple[JointLimit, ...]:
        """Return the limits written by the override, empty before it runs."""
        return self._limits

    def override_joint_ranges(self, limits: Sequence[JointLimit]) -> None:
        """Run the FR-SIM-080 override, then verify it matches the LeRobot limits.

        Args:
            limits: The LeRobot soft limits to write and then verify against.

        Raises:
            IkOrderError: If the override is requested after Kinematics is built —
                it would write onto a limit snapshot no one reads.
            LimitMismatchError: If the readback does not equal the limits.
        """
        if self._stage is BuildStage.KINEMATICS_BUILT:
            raise IkOrderError(
                "jnt_range override requested after Kinematics() was built; the "
                "ConfigurationLimit already snapshotted the un-overridden ranges, so "
                "this write is void (09 FR-SIM-080)"
            )
        if self._stage is BuildStage.RANGE_OVERRIDDEN:
            raise IkOrderError("jnt_range override requested twice on one build")
        overwrite_jnt_range(self._setup, limits)
        verify_ranges_match(self._setup, limits)
        self._limits = tuple(limits)
        self._stage = BuildStage.RANGE_OVERRIDDEN

    def build_kinematics(self, ik_params: IKParams) -> Kinematics:
        """Build ``Kinematics`` once the override has run; reject otherwise.

        Args:
            ik_params: The mink IK parameters for the solver.

        Returns:
            (Kinematics) The solver, built over the overridden model.

        Raises:
            IkOrderError: If the override has not run first (FR-SIM-080), or if a
                Kinematics was already built on this machine.
        """
        if self._stage is BuildStage.SETUP_CREATED:
            raise IkOrderError(
                "Kinematics() requested before the jnt_range override; mink would "
                "snapshot the un-overridden MJCF limits and the override would then "
                "be void (09 FR-SIM-080)"
            )
        if self._stage is BuildStage.KINEMATICS_BUILT:
            raise IkOrderError("Kinematics() already built on this build")
        kinematics = Kinematics(self._setup, ik_params)
        self._stage = BuildStage.KINEMATICS_BUILT
        return kinematics
