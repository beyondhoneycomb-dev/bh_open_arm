"""The v1 friction seed and the per-joint relative-error comparison (acceptance ④).

The only measured friction that exists is v1: `openarm_teleop/config/follower.yaml`, identified
for the v1 arm ten months before the first v2 asset and treated as a seed only (spec 09
FR-SIM-048, spec 12 §2.6). That file is not vendored into this repository. The values below are
representative v1 seed magnitudes for a ~40 Nm arm: they warm-start the fit and exercise the
relative-error comparison. A real PG-FRIC-001 run replaces them with the actual `follower.yaml`
seed, loaded through WP-2B-10's read-only, `robot_version: "1.0"`-tagged seed profile — never
by promoting these placeholders to a v2 runtime value.

The comparison reports, per joint, how far the identified v2 parameters moved from the seed. A
large move is expected and is the point (v2 differs from v1); the table is what acceptance ④
requires so the change is visible rather than assumed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.dynamics.provenance import Provenance
from backend.friction.constants import ARM_JOINT_COUNT
from backend.friction.errors import FrictionIdentificationError
from backend.friction.model import FrictionParams

# Provenance stamp marking the seed as v1: the strict v2 loader (WP-2B-01 / WP-2B-10) refuses a
# `robot_version` other than "2.0", so this stamp keeps the seed out of the v2 runtime by
# construction rather than by anyone remembering it is v1.
V1_SEED_PROVENANCE = Provenance(
    source_repo="enactic/openarm_teleop",
    commit_sha="v1-seed-not-vendored",
    path="config/follower.yaml",
    robot_version="1.0",
    identified_on="2025-07-23",
)

# Representative v1 seed parameters, joint1..joint7. Stored as `(Fo, Fv, Fc, k)` in the YAML
# convention (`k` is the pre-0.1 slope); `FrictionParams.from_stored_k` applies `k_eff = 0.1*k`.
_V1_SEED_STORED = (
    (0.05, 0.40, 1.20, 40.0),
    (0.06, 0.50, 1.50, 40.0),
    (0.04, 0.30, 0.90, 45.0),
    (0.03, 0.25, 0.80, 45.0),
    (0.02, 0.15, 0.40, 50.0),
    (0.02, 0.12, 0.30, 50.0),
    (0.01, 0.08, 0.20, 50.0),
)

# The denominator floor for a relative error whose seed value is near zero (the `Fo` offset can
# be). Below it the relative error would explode on a physically negligible term, so it is
# divided by this floor instead and the result read as an absolute-scale ratio.
_RELATIVE_FLOOR_NM = 1.0e-3

V1_SEED_FRICTION: tuple[FrictionParams, ...] = tuple(
    FrictionParams.from_stored_k(f_o=row[0], f_v=row[1], f_c=row[2], k=row[3])
    for row in _V1_SEED_STORED
)


@dataclass(frozen=True)
class RelativeError:
    """One joint's relative error between identified and seed parameters.

    Attributes:
        joint_index: Zero-based arm joint index (0 = joint1).
        rel_f_o: Relative error of the offset term.
        rel_f_v: Relative error of the viscous term.
        rel_f_c: Relative error of the Coulomb term.
        rel_k_eff: Relative error of the tanh slope.
        rel_l2: L2 relative error over the four-parameter vector.
    """

    joint_index: int
    rel_f_o: float
    rel_f_v: float
    rel_f_c: float
    rel_k_eff: float
    rel_l2: float


def _rel(identified: float, seed: float) -> float:
    """Return `|identified - seed| / max(|seed|, floor)`, guarding a near-zero seed."""
    return abs(identified - seed) / max(abs(seed), _RELATIVE_FLOOR_NM)


def _l2_rel(identified: FrictionParams, seed: FrictionParams) -> float:
    """Return the L2 relative error over `(f_o, f_v, f_c, k_eff)`."""
    diff_sq = (
        (identified.f_o - seed.f_o) ** 2
        + (identified.f_v - seed.f_v) ** 2
        + (identified.f_c - seed.f_c) ** 2
        + (identified.k_eff - seed.k_eff) ** 2
    )
    norm_sq = seed.f_o**2 + seed.f_v**2 + seed.f_c**2 + seed.k_eff**2
    return (diff_sq**0.5) / max(norm_sq**0.5, _RELATIVE_FLOOR_NM)


def relative_error_table(
    identified: Sequence[FrictionParams], seed: Sequence[FrictionParams] = V1_SEED_FRICTION
) -> tuple[RelativeError, ...]:
    """Compute the per-joint relative error of identified parameters against the seed.

    Args:
        identified: The identified per-joint parameters, joint1..joint7 order.
        seed: The seed parameters to compare against; the v1 seed by default.

    Returns:
        (tuple[RelativeError, ...]) One row per joint.

    Raises:
        FrictionIdentificationError: If the two sequences are not both `ARM_JOINT_COUNT` long.
    """
    if len(identified) != ARM_JOINT_COUNT or len(seed) != ARM_JOINT_COUNT:
        raise FrictionIdentificationError(
            f"identified ({len(identified)}) and seed ({len(seed)}) must each have "
            f"{ARM_JOINT_COUNT} entries"
        )
    rows: list[RelativeError] = []
    for index in range(ARM_JOINT_COUNT):
        got = identified[index]
        base = seed[index]
        rows.append(
            RelativeError(
                joint_index=index,
                rel_f_o=_rel(got.f_o, base.f_o),
                rel_f_v=_rel(got.f_v, base.f_v),
                rel_f_c=_rel(got.f_c, base.f_c),
                rel_k_eff=_rel(got.k_eff, base.k_eff),
                rel_l2=_l2_rel(got, base),
            )
        )
    return tuple(rows)


def format_relative_error_table(rows: Sequence[RelativeError]) -> str:
    """Render the relative-error rows as a fixed-width text table.

    Args:
        rows: The per-joint relative-error rows.

    Returns:
        (str) A table with a header and one row per joint.
    """
    header = (
        f"{'joint':>6} {'rel Fo':>9} {'rel Fv':>9} {'rel Fc':>9} {'rel k_eff':>10} {'rel L2':>9}"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            f"{row.joint_index + 1:>6} {row.rel_f_o:>9.4f} {row.rel_f_v:>9.4f} "
            f"{row.rel_f_c:>9.4f} {row.rel_k_eff:>10.4f} {row.rel_l2:>9.4f}"
        )
    return "\n".join(lines)
