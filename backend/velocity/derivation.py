"""The derivation-basis artifact the velocity limiter loads (WP-2A-04, acceptance ②).

A velocity ceiling is only admissible if it can say where it came from. This module
wraps each per-joint magnitude — imported from the WP-1-06 physical canon, never
re-derived here — with its derivation basis: the motor register V_MAX, the gear ratio,
the winning source, and the formula. A limit whose basis is incomplete is load-refused
(`DerivationBasisError`), so a bare number with no provenance can never become an active
ceiling. The magnitudes themselves are the single-source-of-truth
`backend.safety_bringup.velocity.bootstrap_limiter_rad_s()`; this layer adds accountability,
not a second derivation.

`03` §5.6.0 fixes the arithmetic and the ordering: the ceiling is the minimum over the
register V_MAX, the catalogue no-load speed, the URDF velocity limit and the `12` §2.5 cap,
and the hardware register is never permitted to be that minimum (`03` trap 2). The winning
source is recorded per joint so the basis states which physical fact bounded the joint,
not merely that some number was chosen.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS
from backend.safety_bringup.constants import ARM_JOINT_MOTORS, VELOCITY_CAP_RAD_S
from backend.safety_bringup.velocity import (
    VelocitySource,
    bootstrap_limiter_rad_s,
    three_way_table,
)
from backend.velocity.constants import (
    BOOTSTRAP_BASIS_URIS,
    BOOTSTRAP_LIMIT_SET_VERSION,
    GEAR_RATIO_BY_MOTOR,
    PROVENANCE_BOOTSTRAP,
)

# The `12` §2.5 velocity cap, when it undercuts the three-way physical canon, is the
# source that bounded the joint. It is not one of the `VelocitySource` members (those name
# the three physical candidates), so it carries its own label in the artifact.
SOURCE_VELOCITY_CAP = "velocity_cap_12_2_5"


class DerivationBasisError(ValueError):
    """Raised when a velocity limit is loaded without a complete derivation basis.

    Acceptance ② makes a value with no derivation basis load-refused: a ceiling that
    cannot name its formula, gear ratio, motor V_MAX and source is a bare number, and a
    bare number is exactly what the arithmetic-not-measured ordering exists to keep off
    the arm. The error names the offending joint so a caller can attribute the refusal.
    """


@dataclass(frozen=True)
class DerivedLimit:
    """One joint's velocity ceiling together with the basis that authorises it.

    The value is not computed here — it is the WP-1-06 bootstrap magnitude — so this type
    carries the accountability, not the arithmetic. `validate` refuses an entry that omits
    any basis field or that exceeds the motor's own output V_MAX, which no derived joint
    ceiling ever may.

    Attributes:
        joint_index: Zero-based arm joint index (0 == J1).
        motor_type: The motor family at this joint (`DM8009`/`DM4340`/`DM4310`).
        value_rad_s: The conservative velocity ceiling, rad/s — the active limit magnitude.
        motor_vmax_rad_s: The motor register V_MAX (RID 22), the output-shaft ceiling.
        gear_ratio: The mechanical reduction that makes the register an output-side figure.
        source: Which physical fact bounded the joint (the winning minimum).
        formula: The derivation expression, stated so a reader can reproduce the value.
    """

    joint_index: int
    motor_type: str
    value_rad_s: float
    motor_vmax_rad_s: float
    gear_ratio: float
    source: str
    formula: str

    def validate(self) -> None:
        """Refuse a limit whose derivation basis is incomplete or physically impossible.

        Raises:
            DerivationBasisError: When any magnitude is non-positive, any basis field
                (source/formula) is empty, or the ceiling exceeds the motor's own output
                V_MAX — a joint limit cannot be faster than the motor that drives it.
        """
        if self.value_rad_s <= 0.0:
            raise self._error("velocity ceiling is not positive")
        if self.motor_vmax_rad_s <= 0.0:
            raise self._error("motor register V_MAX is not positive")
        if self.gear_ratio <= 0.0:
            raise self._error("gear ratio is not positive")
        if not self.source:
            raise self._error("no derivation source is attached")
        if not self.formula:
            raise self._error("no derivation formula is attached")
        if self.value_rad_s > self.motor_vmax_rad_s:
            raise self._error(
                f"velocity ceiling {self.value_rad_s} exceeds motor output V_MAX "
                f"{self.motor_vmax_rad_s}; a joint limit cannot outrun its motor"
            )

    def _error(self, detail: str) -> DerivationBasisError:
        """Build a basis error naming this joint (a value with no basis is load-refused)."""
        return DerivationBasisError(
            f"joint {self.joint_index} ({self.motor_type}) velocity limit refused: {detail} "
            "(02b §1.2 acceptance ②)"
        )


@dataclass(frozen=True)
class LimitSet:
    """The active velocity-limit set: per-joint ceilings plus the basis of the whole set.

    A limit set is versioned so a refinement can replace it only with a strictly greater
    version (acceptance ⑥), and it carries the physical-source URIs the derivation rests
    on so the self-approval refusal has something to inspect. `validate` runs every joint's
    basis check, so constructing or loading a set with one unbacked joint refuses the set.

    Attributes:
        version: Monotonic set version; a refinement must strictly increase it.
        provenance: `bootstrap` (arithmetic) or `refined` (`PG-VEL-001`-verified).
        basis_uris: The physical-source URIs (datasheet/URDF/catalogue) — never a rig result.
        limits: One `DerivedLimit` per joint, in J1..Jn order.
    """

    version: int
    provenance: str
    basis_uris: tuple[str, ...]
    limits: tuple[DerivedLimit, ...]

    @property
    def width(self) -> int:
        """The number of joints this set declares ceilings for."""
        return len(self.limits)

    @property
    def values_rad_s(self) -> tuple[float, ...]:
        """The per-joint velocity ceilings, rad/s, in joint order."""
        return tuple(limit.value_rad_s for limit in self.limits)

    def validate(self) -> None:
        """Refuse a set with a bad version, no basis, no limits, or one unbacked joint.

        Raises:
            DerivationBasisError: When the version is below one, the provenance or the
                basis-URI list is empty, the set has no joints, or any joint's basis check
                fails — a value with no derivation basis is load-refused.
        """
        if self.version < 1:
            raise DerivationBasisError(f"limit-set version {self.version} is below 1")
        if not self.provenance:
            raise DerivationBasisError("limit set carries no provenance label")
        if not self.basis_uris:
            raise DerivationBasisError(
                "limit set declares no basis URI; a derived set with no cited physical "
                "source cannot be loaded (02b §1.2 acceptance ②)"
            )
        if not self.limits:
            raise DerivationBasisError("limit set declares no joint ceilings")
        for limit in self.limits:
            limit.validate()


def _winning_source(canon_source: VelocitySource, canon_rad_s: float, cap_rad_s: float) -> str:
    """Name the fact that bounded a joint: the three-way canon, or the `12` §2.5 cap.

    Args:
        canon_source: The source that won the three-way physical minimum.
        canon_rad_s: The three-way physical canon value.
        cap_rad_s: The `12` §2.5 velocity cap for the joint.

    Returns:
        (str) The winning source label — the cap only when it strictly undercuts the canon.
    """
    if cap_rad_s < canon_rad_s:
        return SOURCE_VELOCITY_CAP
    return canon_source.value


def _bootstrap_formula(
    row_register_rad_s: float,
    catalogue_rad_s: float | None,
    urdf_rad_s: float,
    cap_rad_s: float,
    gear_ratio: float,
) -> str:
    """State the per-joint derivation formula (`03` §5.6.0 ①②) for the artifact.

    Args:
        row_register_rad_s: The motor register V_MAX (output-shaft).
        catalogue_rad_s: The catalogue no-load speed, or None when the corpus quotes none.
        urdf_rad_s: The URDF velocity limit.
        cap_rad_s: The `12` §2.5 velocity cap.
        gear_ratio: The mechanical reduction the register already embodies.

    Returns:
        (str) The minimum-over-sources formula, with the register's output-shaft note.
    """
    catalogue = "absent" if catalogue_rad_s is None else f"{catalogue_rad_s}"
    return (
        f"ceiling = min(register_vmax={row_register_rad_s} [output-shaft, gear {gear_ratio}:1], "
        f"catalogue_no_load={catalogue}, urdf_velocity={urdf_rad_s}, cap_12_2_5={cap_rad_s}); "
        "register never permitted as the minimum (03 trap 2 / §5.6.0)"
    )


def bootstrap_limit_set() -> LimitSet:
    """Build the bootstrap-conservative limit set: WP-1-06 magnitudes with WP-2A-04 basis.

    The magnitudes come from `bootstrap_limiter_rad_s()` — this function does not re-derive
    them — and each is wrapped with the register V_MAX, the gear ratio, the winning source
    and the formula so it can survive `LimitSet.validate`. The winning source is recomputed
    from the three-way table and the `12` §2.5 cap so the basis records which physical fact
    bounded each joint, not merely that a number was picked.

    Returns:
        (LimitSet) The version-1 bootstrap set, validated, ready to arm the limiter.
    """
    table = three_way_table()
    bootstrap = bootstrap_limiter_rad_s()
    limits: list[DerivedLimit] = []
    for index, row in enumerate(table):
        motor = ARM_JOINT_MOTORS[index]
        register_vmax = MOTOR_LIMIT_PARAMS[motor].v_max
        gear_ratio = GEAR_RATIO_BY_MOTOR[motor]
        cap = VELOCITY_CAP_RAD_S[index]
        value = bootstrap[index]
        # Defensive: the imported magnitude must equal the minimum this basis describes,
        # or the artifact would attach a formula that does not produce the value it labels.
        expected = min(row.canon_rad_s, cap)
        if value != expected:
            raise DerivationBasisError(
                f"joint {index} bootstrap magnitude {value} disagrees with its basis "
                f"minimum {expected}; the artifact would misdescribe the value"
            )
        limits.append(
            DerivedLimit(
                joint_index=index,
                motor_type=motor.value,
                value_rad_s=value,
                motor_vmax_rad_s=register_vmax,
                gear_ratio=gear_ratio,
                source=_winning_source(row.canon_source, row.canon_rad_s, cap),
                formula=_bootstrap_formula(
                    register_vmax,
                    row.catalogue_no_load_rad_s,
                    row.urdf_velocity_rad_s,
                    cap,
                    gear_ratio,
                ),
            )
        )
    limit_set = LimitSet(
        version=BOOTSTRAP_LIMIT_SET_VERSION,
        provenance=PROVENANCE_BOOTSTRAP,
        basis_uris=BOOTSTRAP_BASIS_URIS,
        limits=tuple(limits),
    )
    limit_set.validate()
    return limit_set
