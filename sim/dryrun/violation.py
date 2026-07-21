"""The six dry-run checks as distinct item codes, and the violation record.

`09` FR-SIM-030 fixes exactly six dry-run checks, and acceptance ② forbids
collapsing them into one "dry-run failed" verdict: each check owns one
``OA-DRY-00x`` item code so a report always says *which* limit was crossed. A
merged code would hide that link5 hit the table rather than exceeded a torque
bound, and those demand different operator responses.

`09` FR-SIM-033 fixes the violation record's four fields — item, sim time,
implicated joint, and overage — and this module is where that shape is frozen.
For a per-joint check the ``joint`` field is the motor key; for a collision the
locus is a geom pair rather than one joint, so the same field carries the pair
label (there is no single joint a penetration belongs to). ``overage`` is always
a non-negative magnitude in the check's own unit: radians past a position bound,
radians/second past a velocity bound, newton-metres past a torque bound, metres
of penetration for a collision, metres past the lifter stroke.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DryRunCheck(Enum):
    """One member per FR-SIM-030 check; the value is its ``OA-DRY-*`` item code.

    Six distinct members so a reporter cannot merge two checks into a single
    "dry-run failure" bucket (acceptance ②, `09` FR-SIM-030 forbids exactly that).
    """

    POSITION_LIMIT = "OA-DRY-001"
    VELOCITY_LIMIT = "OA-DRY-002"
    TORQUE_LIMIT = "OA-DRY-003"
    CELL_COLLISION = "OA-DRY-004"
    SELF_COLLISION = "OA-DRY-005"
    LIFTER_STROKE = "OA-DRY-006"


@dataclass(frozen=True)
class Violation:
    """One dry-run violation, carrying the four FR-SIM-033 fields.

    Attributes:
        item: Which of the six checks fired (its ``OA-DRY-*`` code is the value).
        sim_t: Simulation time in seconds at which the violation occurred.
        joint: The implicated locus — a motor key for a per-joint check, or a
            ``geom_a<->geom_b`` pair label for a collision, which has no single
            joint.
        overage: How far the limit was exceeded, a non-negative magnitude in the
            check's own unit (rad, rad/s, Nm, or metres).
    """

    item: DryRunCheck
    sim_t: float
    joint: str
    overage: float


@dataclass(frozen=True)
class DryRunVerdict:
    """The outcome of validating one trajectory against all six checks.

    A verdict is *passing* exactly when it carries no violations; that is the sole
    condition under which the interlock grants real transmission without a modal
    confirmation (`09` FR-SIM-033). ``asset_digest`` records which fixed MJCF the
    dry-run resolved over, so the verdict names the asset its judgement is bound to
    (acceptance ⑮).

    Attributes:
        violations: Every violation found, across all waypoints and checks.
        asset_digest: The content digest of the WP-0C-03 fixed asset the run used.
        backend: The backend the hard gate ran on; MuJoCo is the canonical gate.
    """

    violations: tuple[Violation, ...] = ()
    asset_digest: str = ""
    backend: str = ""

    @property
    def passed(self) -> bool:
        """Whether the trajectory cleared every check (no violation recorded)."""
        return not self.violations

    def items_hit(self) -> tuple[DryRunCheck, ...]:
        """Return the distinct checks that fired, in first-seen order.

        Returns:
            (tuple[DryRunCheck, ...]) Distinct violated checks; empty when passing.
        """
        seen: list[DryRunCheck] = []
        for violation in self.violations:
            if violation.item not in seen:
                seen.append(violation.item)
        return tuple(seen)
