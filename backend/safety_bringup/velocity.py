"""PG-VEL-001 — the joint velocity canon, derived by arithmetic, never measured.

`03` §5.6.0 fixes the order: a safety velocity limit is *derived* from physics first, and
the rig is then measured against it — the gate asks "does the joint follow command under
the derived limit", not "how fast can this joint go". Two facts make this module's shape:

  * The canon is the MINIMUM of three sources — register V_MAX, catalogue no-load speed,
    and the URDF velocity limit — never the register alone. The register is deliberately
    not authoritative: for the DM4340 (J3/J4) its V_MAX of 8 rad/s exceeds both the
    catalogue (5.45) and the URDF (5.4454), so taking it would let the hardware declare
    its own safety ceiling (`03` trap 2). The three-way table exists to prove, per joint,
    that the register is never the minimum.
  * The bootstrap limiter overlays the `12` §2.5 velocity cap onto that physical minimum
    and takes the minimum again (`03` §5.6.0 ②). This is the limiter `WP-2A-04` stands up
    first, before this gate ever runs, so the sweep runs under protection.

This module derives; it does not sweep. The command-following sweep (⑨-a/⑨-b) needs the
powered arm and is deferred to `sweep`/`reverify`. What runs here is the arithmetic: the
three-way table, the register-is-never-canon proof, the bootstrap limiter, and the
self-approval refusal — a derivation basis that points at the gate's own result record is
FAIL_BLOCKING (`03` §5.6 / §1.1), because a limit that cites its own measurement is the
circular self-approval the whole ordering exists to forbid.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS
from backend.safety_bringup.constants import (
    ARM_JOINT_COUNT,
    ARM_JOINT_MOTORS,
    CATALOGUE_NO_LOAD_SPEED_RAD_S,
    URDF_VELOCITY_LIMIT_RAD_S,
    VELOCITY_CAP_RAD_S,
)


class VelocitySource(Enum):
    """The provenance of a derived joint velocity limit.

    `REGISTER` is present in the vocabulary precisely so a canon that resolves to it can be
    named and refused — hardware may not be the source of its own safety limit (`03` trap 2).
    """

    REGISTER = "register_vmax"
    CATALOGUE = "catalogue_no_load"
    URDF = "urdf_velocity_limit"


class DerivationSelfApprovalError(Exception):
    """Raised when a velocity derivation cites its own result record as its basis.

    A limit whose justification points at the sweep it is supposed to authorise is the
    self-approval `03` §5.6/§1.1 makes FAIL_BLOCKING: the derivation must rest on the
    datasheet, the URDF and the catalogue, never on the gate's own measurement.
    """


@dataclass(frozen=True)
class ThreeWayRow:
    """One joint's three candidate velocity limits and the physical minimum among them.

    Attributes:
        joint_index: Zero-based arm joint index (0 == J1).
        register_vmax_rad_s: The motor register V_MAX at this joint (`MOTOR_LIMIT_PARAMS`).
        catalogue_no_load_rad_s: The catalogue max no-load speed, or None when the corpus
            quotes none for this motor — an absent candidate, never an invented one.
        urdf_velocity_rad_s: The URDF joint velocity limit.
        canon_rad_s: The minimum over the present candidates — the physical derivation.
        canon_source: Which source the minimum came from.
    """

    joint_index: int
    register_vmax_rad_s: float
    catalogue_no_load_rad_s: float | None
    urdf_velocity_rad_s: float
    canon_rad_s: float
    canon_source: VelocitySource

    @property
    def register_is_canon(self) -> bool:
        """Whether the register V_MAX is the physical minimum at this joint.

        Returns:
            (bool) True only if the register won the minimum — the forbidden case in
            which hardware would define its own safety ceiling (`03` trap 2).
        """
        return self.canon_source is VelocitySource.REGISTER


def _canon_for_joint(joint_index: int) -> ThreeWayRow:
    """Derive one joint's velocity canon as the minimum of its present candidates.

    Args:
        joint_index: Zero-based arm joint index.

    Returns:
        (ThreeWayRow) The three candidates and their minimum with its provenance.
    """
    motor = ARM_JOINT_MOTORS[joint_index]
    register = MOTOR_LIMIT_PARAMS[motor].v_max
    catalogue = CATALOGUE_NO_LOAD_SPEED_RAD_S.get(motor)
    urdf = URDF_VELOCITY_LIMIT_RAD_S[joint_index]

    candidates: list[tuple[float, VelocitySource]] = [
        (register, VelocitySource.REGISTER),
        (urdf, VelocitySource.URDF),
    ]
    if catalogue is not None:
        candidates.append((catalogue, VelocitySource.CATALOGUE))

    canon_value, canon_source = min(candidates, key=_candidate_value)
    return ThreeWayRow(
        joint_index=joint_index,
        register_vmax_rad_s=register,
        catalogue_no_load_rad_s=catalogue,
        urdf_velocity_rad_s=urdf,
        canon_rad_s=canon_value,
        canon_source=canon_source,
    )


def _candidate_value(candidate: tuple[float, VelocitySource]) -> float:
    """Key a `(value, source)` candidate by its numeric value for the minimum.

    Args:
        candidate: The `(value, source)` pair.

    Returns:
        (float) The candidate's velocity value.
    """
    return candidate[0]


def three_way_table() -> tuple[ThreeWayRow, ...]:
    """Build the per-joint three-way comparison (⑨-c): register / catalogue / URDF -> min.

    Returns:
        (tuple[ThreeWayRow, ...]) One row per arm joint, in J1..J7 order.
    """
    return tuple(_canon_for_joint(index) for index in range(ARM_JOINT_COUNT))


def assert_register_never_canon(table: tuple[ThreeWayRow, ...]) -> None:
    """Refuse a derivation in which the register V_MAX is any joint's canon (⑨-c).

    The register winning the minimum means the hardware defined its own ceiling, which the
    whole derivation exists to prevent (`03` trap 2). At least the DM4340 joints must
    resolve away from the register (register 8 > URDF 5.4454), and none may resolve to it.

    Args:
        table: The three-way table.

    Raises:
        DerivationSelfApprovalError: If any joint's canon source is the register.
    """
    offenders = [row.joint_index for row in table if row.register_is_canon]
    if offenders:
        raise DerivationSelfApprovalError(
            f"joints {offenders} resolved their velocity canon to the register V_MAX; "
            "hardware cannot be the source of its own safety limit (03 §5.6.0 / trap 2)"
        )


def physical_canon_rad_s() -> tuple[float, ...]:
    """The step-① physical velocity canon per joint — the three-way minimum (`03` §5.6.0 ①).

    Returns:
        (tuple[float, ...]) Per-joint physical velocity canon, rad/s.
    """
    return tuple(row.canon_rad_s for row in three_way_table())


def bootstrap_limiter_rad_s() -> tuple[float, ...]:
    """The step-② bootstrap limiter: physical canon overlaid with the `12` §2.5 cap.

    `03` §5.6.0 ② conservatises the physical derivation by taking the minimum again against
    the velocity cap. This is the limiter `WP-2A-04` stands up first (③), so a sweep never
    runs unprotected.

    Returns:
        (tuple[float, ...]) Per-joint bootstrap velocity limit, rad/s.
    """
    return tuple(
        min(canon, cap)
        for canon, cap in zip(physical_canon_rad_s(), VELOCITY_CAP_RAD_S, strict=True)
    )


@dataclass(frozen=True)
class VelocityLimiterDefault:
    """The default state of the arm velocity limiter (`12` §2.5, acceptance ⑩).

    Upstream, `ARM_JOINT_VELOCITY_LIMITS_RAD_S` is active only behind `--limit-velocity`
    and the default is no limit at all (`16` §11 trap 7). WP-1-06 flips that default on,
    so the limiter stands at the bootstrap values with no flag required.

    Attributes:
        active: True — the limiter is active by default (the flip).
        limits_rad_s: The per-joint velocity ceiling the default limiter enforces.
    """

    active: bool
    limits_rad_s: tuple[float, ...]


def velocity_limiter_default() -> VelocityLimiterDefault:
    """Return the WP-1-06 default velocity-limiter state: active, at bootstrap values (⑩).

    Returns:
        (VelocityLimiterDefault) Active-by-default limiter carrying the bootstrap limits.
    """
    return VelocityLimiterDefault(active=True, limits_rad_s=bootstrap_limiter_rad_s())


def assert_velocity_limit_active_by_default(default: VelocityLimiterDefault) -> None:
    """Refuse a velocity limiter that is not active by default (`12` §2.5, acceptance ⑩).

    Args:
        default: The declared default limiter state.

    Raises:
        ValueError: If the limiter is not active by default — the upstream no-limit default
            we exist to flip.
    """
    if not default.active:
        raise ValueError(
            "arm velocity limiter is not active by default; WP-1-06 flips the upstream "
            "no-limit default on (12 §2.5, 16 §11 trap 7, acceptance ⑩)"
        )


def assert_derivation_basis_not_self(basis_uris: tuple[str, ...], result_record_uri: str) -> None:
    """Refuse a derivation basis that points at the gate's own result record (⑨-d).

    The basis must be the physical sources — datasheet, URDF, catalogue, gear ratios. A
    basis URI equal to (or under) the result record is the self-approval `03` §5.6/§1.1
    makes FAIL_BLOCKING.

    Args:
        basis_uris: The declared derivation-basis URIs.
        result_record_uri: The URI of this gate's own result record.

    Raises:
        DerivationSelfApprovalError: If the basis is empty, or any basis URI is the result
            record or a path under it.
    """
    if not basis_uris:
        raise DerivationSelfApprovalError(
            "velocity derivation declares no basis URI; a derived limit with no cited "
            "physical source cannot be sealed (03 §5.6 acceptance ⑨-d)"
        )
    normalized_result = result_record_uri.rstrip("/")
    for uri in basis_uris:
        normalized = uri.rstrip("/")
        if normalized == normalized_result or normalized.startswith(normalized_result + "/"):
            raise DerivationSelfApprovalError(
                f"derivation basis {uri!r} points at the gate's own result record "
                f"{result_record_uri!r}; a limit that cites its own measurement is "
                "self-approval (03 §5.6 / §1.1, FAIL_BLOCKING)"
            )
