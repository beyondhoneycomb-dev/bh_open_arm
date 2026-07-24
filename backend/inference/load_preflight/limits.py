"""The v2 URDF limit loader: read once, inject into two places (FR-INF-036).

This is the WP-4B-03 limit-loader deliverable. `load_canonical_limits` reads
`joint_limits.yaml` exactly once into a `CanonicalLimits`, and both injection
targets derive from that one object so they cannot become two truths:

  (a) `config_openarm_follower.joint_limits` (degrees) — `apply_to_follower_config`;
  (b) the IK MJCF `jnt_range` (radians) — `build_canonical_ik_adapter`, which drives
      the committed `OrderedIkBuild` so the override lands BEFORE `Kinematics(...)`
      (09 FR-SIM-080: `mink.ConfigurationLimit` snapshots `jnt_range` at construction,
      so a write after `Kinematics` is void).

The MJCF override reuses the committed `sim.ik` APIs unchanged — `ArmSetup`,
`OrderedIkBuild`, `IkAdapter`, the fixed cell asset — swapping only the limit source
from LeRobot's soft defaults (`all_soft_limits`) to the canon read here. It never
edits those files; the canon is injected at runtime.

The degrees the config receives and the radians the MJCF receives are the same
numbers in two units, produced from the single `CanonicalLimits` through the one
sanctioned CTR-UNIT `rad_to_deg` crossing, so `verify_two_place_consistency` compares
them and a divergence is a hard failure, not a warning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from contracts.units.conversions import rad_to_deg
from contracts.units.tags import Rad
from sim.ik.limits import ARM_JOINT_KEYS, GRIPPER_KEY, SIDES, JointLimit

if TYPE_CHECKING:
    import mujoco
    from openarm_control.config import ArmSetup
    from openarm_control.kinematics import IKParams

    from sim.ik.adapter import IkAdapter

# The canonical source file: sibling of this module, so the loader is independent of
# the working directory (the same discipline the IK asset uses for the MJCF).
CANONICAL_YAML = Path(__file__).resolve().parent / "joint_limits.yaml"

# LeRobot limit-dict key -> MJCF joint-name suffix. The arm keys index by number; the
# gripper key names the finger driver joint. This mirrors `sim.ik.limits._MJCF_SUFFIX`
# (private there); it is the joint the override writes and the adapter clamps to.
_MJCF_SUFFIX: dict[str, str] = {
    "joint_1": "joint1",
    "joint_2": "joint2",
    "joint_3": "joint3",
    "joint_4": "joint4",
    "joint_5": "joint5",
    "joint_6": "joint6",
    "joint_7": "joint7",
    GRIPPER_KEY: "finger_joint1",
}

# The eight per-arm keys in canonical order: seven arm joints then the gripper. The
# order is the contract with the driver layout, named once rather than re-spelled.
_MOTOR_KEYS: tuple[str, ...] = (*ARM_JOINT_KEYS, GRIPPER_KEY)

# jnt_range readback tolerance (rad). The override writes the exact radian floats the
# canon carries, so a real match is bit-exact; this only absorbs the deg<->rad
# round-trip used to compare the config-degrees place against the MJCF-radians place.
TWO_PLACE_TOLERANCE_DEG = 1e-6

_ARM_PREFIX = "openarm_"


class CanonicalLimitError(RuntimeError):
    """Raised when `joint_limits.yaml` is missing a side, a joint, or a bound.

    A partial canon is worse than none: it would inject a full-canon limit on some
    joints and leave the LeRobot soft (or +/-5 degree) default on others, which is
    exactly the split-truth this loader exists to prevent.
    """


@dataclass(frozen=True)
class CanonicalLimits:
    """The v2 URDF mechanical limits, read once from `joint_limits.yaml` (radians).

    Attributes:
        per_side: `side` -> `motor_key` -> `(lower_rad, upper_rad)`, both sides
            present and every one of the eight motor keys present per side.
    """

    per_side: Mapping[str, Mapping[str, tuple[float, float]]]

    def bounds_rad(self, side: str, key: str) -> tuple[float, float]:
        """Return one joint's `(lower_rad, upper_rad)` for a side."""
        return self.per_side[side][key]


def load_canonical_limits(path: Path = CANONICAL_YAML) -> CanonicalLimits:
    """Read `joint_limits.yaml` once into a validated `CanonicalLimits` (radians).

    Args:
        path: The canon file; defaults to the module's own `joint_limits.yaml`.

    Returns:
        (CanonicalLimits) Both sides, all eight motor keys, radian bounds.

    Raises:
        CanonicalLimitError: When a side, a joint, or a numeric bound is missing.
    """
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise CanonicalLimitError(f"{path} is not a mapping")
    table = document.get("joint_limits")
    if not isinstance(table, dict):
        raise CanonicalLimitError(f"{path} has no 'joint_limits' mapping")

    per_side: dict[str, dict[str, tuple[float, float]]] = {}
    for side in SIDES:
        side_table = table.get(side)
        if not isinstance(side_table, dict):
            raise CanonicalLimitError(f"{path}: side {side!r} missing")
        resolved: dict[str, tuple[float, float]] = {}
        for key in _MOTOR_KEYS:
            resolved[key] = _read_bounds(path, side, key, side_table.get(key))
        per_side[side] = resolved
    return CanonicalLimits(per_side=per_side)


def _read_bounds(path: Path, side: str, key: str, raw: object) -> tuple[float, float]:
    """Coerce one `[lower, upper]` yaml entry to a radian bound pair, or reject."""
    if not isinstance(raw, Sequence) or isinstance(raw, str) or len(raw) != 2:
        raise CanonicalLimitError(f"{path}: {side}.{key} must be [lower, upper], got {raw!r}")
    lower, upper = float(raw[0]), float(raw[1])
    if lower > upper:
        raise CanonicalLimitError(f"{path}: {side}.{key} lower {lower} exceeds upper {upper}")
    return (lower, upper)


def config_joint_limits_deg(
    canonical: CanonicalLimits, side: str
) -> dict[str, tuple[float, float]]:
    """Derive place (a): the follower config's `joint_limits` dict in degrees.

    Args:
        canonical: The one canon read by `load_canonical_limits`.
        side: `"right"` or `"left"`.

    Returns:
        (dict[str, tuple[float, float]]) `motor_key` -> `(lo_deg, hi_deg)`, the shape
            `config_openarm_follower.joint_limits` uses.
    """
    resolved: dict[str, tuple[float, float]] = {}
    for key in _MOTOR_KEYS:
        lower_rad, upper_rad = canonical.bounds_rad(side, key)
        resolved[key] = (rad_to_deg(Rad(lower_rad)).value, rad_to_deg(Rad(upper_rad)).value)
    return resolved


def apply_to_follower_config(canonical: CanonicalLimits, config: Any, side: str) -> None:
    """Inject place (a): overwrite a follower config's `joint_limits` with the canon.

    The LeRobot follower keeps its v1-era soft `joint_limits` (or the +/-5 degree lock
    when `side` is unset) until this runs; this replaces them with the v2 canon in
    degrees, read from the same object the MJCF override reads.

    Args:
        canonical: The one canon.
        config: A `config_openarm_follower` config object with a `joint_limits` attr.
        side: `"right"` or `"left"`.
    """
    config.joint_limits = config_joint_limits_deg(canonical, side)


def canonical_ik_jointlimits(
    canonical: CanonicalLimits, arm_prefix: str = _ARM_PREFIX
) -> tuple[JointLimit, ...]:
    """Derive place (b) inputs: per-side `JointLimit`s for the MJCF `jnt_range` override.

    Ordered right-arm-then-left-arm, eight joints each, matching the committed
    `sim.ik.limits.all_soft_limits` layout so the override and the adapter's output
    clamp index the same joints — only the values are the canon, not the soft limits.

    Args:
        canonical: The one canon.
        arm_prefix: MJCF joint-name prefix (`openarm_` for the v2 asset).

    Returns:
        (tuple[JointLimit, ...]) Sixteen limits, each carrying both units.
    """
    resolved: list[JointLimit] = []
    for side in SIDES:
        for key in _MOTOR_KEYS:
            lower_rad, upper_rad = canonical.bounds_rad(side, key)
            resolved.append(
                JointLimit(
                    mjcf_joint=f"{arm_prefix}{side}_{_MJCF_SUFFIX[key]}",
                    lower_deg=rad_to_deg(Rad(lower_rad)),
                    upper_deg=rad_to_deg(Rad(upper_rad)),
                    lower_rad=Rad(lower_rad),
                    upper_rad=Rad(upper_rad),
                )
            )
    return tuple(resolved)


@dataclass(frozen=True)
class CanonicalIkBuild:
    """The result of a canon-injected IK build, exposing the model for verification.

    Attributes:
        adapter: The ready `IkAdapter` over the canon-overridden model.
        setup: The `ArmSetup` whose `model.jnt_range` now carries the canon (place b).
        limits: The sixteen canonical `JointLimit`s written and clamped to.
    """

    adapter: IkAdapter
    setup: ArmSetup
    limits: tuple[JointLimit, ...]


def build_canonical_ik_adapter(
    canonical: CanonicalLimits | None = None,
    xml: str | None = None,
    mode: str = "bimanual",
    ik_params: IKParams | None = None,
) -> CanonicalIkBuild:
    """Inject place (b): write the canon into the MJCF `jnt_range` BEFORE `Kinematics`.

    Mirrors the committed `sim.ik.build_ik_adapter` exactly, substituting the limit
    source: `OrderedIkBuild` enforces `ArmSetup -> override -> Kinematics`, so the
    canon is snapshotted by `mink.ConfigurationLimit` rather than the un-overridden
    ranges (09 FR-SIM-080). The unconstrained fallback stays off (12 FR-SAF-016).

    Args:
        canonical: The one canon; read from `joint_limits.yaml` when None.
        xml: MJCF path; None uses the committed WP-0C-03 fixed cell asset.
        mode: `"right"`, `"left"`, or `"bimanual"` (bimanual writes all sixteen).
        ik_params: mink IK parameters; None uses `openarm_control` defaults.

    Returns:
        (CanonicalIkBuild) The adapter, its setup, and the canonical limits.

    Raises:
        LimitMismatchError: When the post-override `jnt_range` does not equal the canon.
        IkOrderError: If the committed builder's order contract is violated.
    """
    from openarm_control.config import ArmSetup
    from openarm_control.kinematics import IKParams

    from sim.ik.adapter import IkAdapter
    from sim.ik.asset import (
        EE_FRAME_TYPE,
        HOME_KEYFRAME,
        LEFT_EE_SITE,
        RIGHT_EE_SITE,
        fixed_cell_xml,
    )
    from sim.ik.override import OrderedIkBuild

    resolved = canonical if canonical is not None else load_canonical_limits()
    limits = canonical_ik_jointlimits(resolved)
    asset = xml if xml is not None else str(fixed_cell_xml())
    setup = ArmSetup.from_args(
        xml=asset,
        mode=mode,
        frame_right=RIGHT_EE_SITE,
        frame_type_right=EE_FRAME_TYPE,
        frame_left=LEFT_EE_SITE,
        frame_type_left=EE_FRAME_TYPE,
        keyframe=HOME_KEYFRAME,
    )
    build = OrderedIkBuild(setup)
    build.override_joint_ranges(limits)
    kinematics = build.build_kinematics(ik_params if ik_params is not None else IKParams())
    adapter = IkAdapter(
        kinematics=kinematics,
        setup=setup,
        limits=limits,
        allow_unconstrained_fallback=False,
        residual_max_m=None,
    )
    return CanonicalIkBuild(adapter=adapter, setup=setup, limits=limits)


@dataclass(frozen=True)
class TwoPlaceMismatch:
    """One joint whose config-degrees place disagrees with its MJCF-radians place."""

    mjcf_joint: str
    config_deg: tuple[float, float]
    mjcf_deg: tuple[float, float]


@dataclass(frozen=True)
class TwoPlaceReport:
    """The consistency verdict between the two injection places for one side.

    Attributes:
        ok: True when every joint's config degrees equal the MJCF radians (as degrees).
        mismatches: The diverging joints; empty when `ok`.
    """

    ok: bool
    mismatches: tuple[TwoPlaceMismatch, ...]


def verify_two_place_consistency(
    canonical: CanonicalLimits,
    model: mujoco.MjModel,
    side: str,
    arm_prefix: str = _ARM_PREFIX,
    tolerance_deg: float = TWO_PLACE_TOLERANCE_DEG,
) -> TwoPlaceReport:
    """Assert the config-degrees and MJCF-radians places agree for one arm.

    Both places derive from `canonical`; this reads the model's `jnt_range` back and
    compares it (converted to degrees) against `config_joint_limits_deg`, so a
    divergence between IK's limit source and send_action's clamp source is caught.

    Args:
        canonical: The one canon both places were built from.
        model: The MuJoCo model whose `jnt_range` carries place (b).
        side: `"right"` or `"left"`.
        arm_prefix: MJCF joint-name prefix.
        tolerance_deg: Absolute degree tolerance for the comparison.

    Returns:
        (TwoPlaceReport) Whether the two places agree, and any mismatches.
    """
    import mujoco

    config_deg = config_joint_limits_deg(canonical, side)
    mismatches: list[TwoPlaceMismatch] = []
    for key in _MOTOR_KEYS:
        mjcf_joint = f"{arm_prefix}{side}_{_MJCF_SUFFIX[key]}"
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, mjcf_joint)
        if jid < 0:
            mismatches.append(TwoPlaceMismatch(mjcf_joint, config_deg[key], (float("nan"),) * 2))
            continue
        lo_rad = float(model.jnt_range[jid][0])
        hi_rad = float(model.jnt_range[jid][1])
        mjcf_deg = (rad_to_deg(Rad(lo_rad)).value, rad_to_deg(Rad(hi_rad)).value)
        expected = config_deg[key]
        if (
            abs(mjcf_deg[0] - expected[0]) > tolerance_deg
            or abs(mjcf_deg[1] - expected[1]) > tolerance_deg
        ):
            mismatches.append(TwoPlaceMismatch(mjcf_joint, expected, mjcf_deg))
    return TwoPlaceReport(ok=not mismatches, mismatches=tuple(mismatches))
