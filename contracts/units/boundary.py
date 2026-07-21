"""The rad-deg boundary declaration table and its structural checks.

`contracts/unit_tags.yaml` is the frozen declaration of every place a physical
quantity crosses between degree and radian units, and of the single site that
owns each crossing. This module reads that table and enforces the two invariants
the plan puts on it (`FR-SIM-082`, WP-0A-04 acceptance):

- Every named rad-deg boundary is covered: LeRobot<->openarm_control,
  LeRobot<->MJCF, VR<->IK, CAN<->gateway. A crossing at a boundary the table does
  not declare is a violation (checked against source by `contracts.units.checker`).
- A boundary has exactly one conversion site. Two sites for one boundary is the
  origin of the double-conversion bug, so a duplicate boundary row, an empty site,
  or a site shared between two boundaries is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from contracts.units.tags import Deg, DegPerSec, Nm, PacketTorque, Rad, RadPerSec

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "unit_tags.yaml"

# The rad-deg boundaries the plan enumerates; the table must cover all of them.
REQUIRED_BOUNDARIES = (
    "lerobot<->openarm_control",
    "lerobot<->mjcf",
    "vr<->ik",
    "can<->gateway",
)

# The tag types this contract freezes, by name. Sourced here so the boundary
# table and the static checker agree on the vocabulary without a second list.
TAG_TYPE_NAMES = (
    Deg.__name__,
    Rad.__name__,
    DegPerSec.__name__,
    RadPerSec.__name__,
    Nm.__name__,
    PacketTorque.__name__,
)

# The named conversion functions; a crossing may name only one of these.
CONVERSION_NAMES = (
    "deg_to_rad",
    "rad_to_deg",
    "deg_per_sec_to_rad_per_sec",
    "rad_per_sec_to_deg_per_sec",
)


@dataclass(frozen=True)
class Crossing:
    """One unit crossing a boundary performs.

    Attributes:
        conversion: Named conversion function that performs the crossing.
        source_unit: Tag type the value carries entering the crossing.
        target_unit: Tag type the value carries leaving the crossing.
    """

    conversion: str
    source_unit: str
    target_unit: str


@dataclass(frozen=True)
class Boundary:
    """One declared rad-deg boundary and the single site that owns it.

    Attributes:
        name: Boundary identifier, e.g. `lerobot<->openarm_control`.
        conversion_site: Fully-qualified function name allowed to convert here.
        crossings: The unit crossings this boundary performs.
        spec_ref: The specification clause the boundary derives from.
    """

    name: str
    conversion_site: str
    crossings: tuple[Crossing, ...]
    spec_ref: str


@dataclass(frozen=True)
class BoundaryTable:
    """The parsed boundary declaration table.

    Attributes:
        boundaries: Declared boundaries in file order.
    """

    boundaries: tuple[Boundary, ...]

    def sites(self) -> tuple[str, ...]:
        """Return the conversion-site qualnames the table sanctions.

        Returns:
            (tuple[str, ...]) One site per boundary, in file order.
        """
        return tuple(boundary.conversion_site for boundary in self.boundaries)


def load_boundary_table(path: Path = CONTRACT_PATH) -> BoundaryTable:
    """Parse the boundary declaration table from the frozen contract YAML.

    Args:
        path: Location of `contracts/unit_tags.yaml`.

    Returns:
        (BoundaryTable) The parsed table, unvalidated. Call
        `validate_boundary_table` to enforce coverage and single-site invariants.
    """
    document: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parse_boundary_table(document)


def parse_boundary_table(document: dict[str, Any]) -> BoundaryTable:
    """Build a `BoundaryTable` from an already-loaded contract document.

    Kept separate from `load_boundary_table` so the invariant checks can run over
    an in-memory fixture without a temporary file.

    Args:
        document: Parsed contract mapping with a `boundaries` list.

    Returns:
        (BoundaryTable) The parsed table.
    """
    boundaries: list[Boundary] = []
    for raw in document.get("boundaries", []) or []:
        crossings = tuple(
            Crossing(
                conversion=str(item.get("conversion", "")),
                source_unit=str(item.get("from", "")),
                target_unit=str(item.get("to", "")),
            )
            for item in raw.get("crossings", []) or []
        )
        boundaries.append(
            Boundary(
                name=str(raw.get("boundary", "")),
                conversion_site=str(raw.get("conversion_site", "")),
                crossings=crossings,
                spec_ref=str(raw.get("spec_ref", "")),
            )
        )
    return BoundaryTable(boundaries=tuple(boundaries))


def validate_boundary_table(table: BoundaryTable) -> tuple[str, ...]:
    """Return every way the boundary table violates its invariants.

    The checks are the acceptance criteria of WP-0A-04, items 4 and 5:

    - Coverage: each required rad-deg boundary appears exactly once.
    - Single site: no boundary name repeats (two rows are two sites for one
      boundary), every site is non-empty, and no site is shared across boundaries.
    - Vocabulary: every crossing names a declared conversion function and declared
      tag types, so a boundary cannot smuggle in an unknown conversion.

    Args:
        table: The parsed boundary table.

    Returns:
        (tuple[str, ...]) One message per violation; empty when the table is valid.
    """
    violations: list[str] = []

    seen_names: dict[str, int] = {}
    for boundary in table.boundaries:
        seen_names[boundary.name] = seen_names.get(boundary.name, 0) + 1
    for name, count in seen_names.items():
        if count > 1:
            violations.append(
                f"boundary '{name}' is declared {count} times: a boundary owns exactly one site"
            )

    for required in REQUIRED_BOUNDARIES:
        if required not in seen_names:
            violations.append(f"required boundary '{required}' is not declared")

    sites: dict[str, str] = {}
    for boundary in table.boundaries:
        if not boundary.conversion_site:
            violations.append(f"boundary '{boundary.name}' declares no conversion site")
        elif boundary.conversion_site in sites and sites[boundary.conversion_site] != boundary.name:
            violations.append(
                f"conversion site '{boundary.conversion_site}' is shared by boundaries "
                f"'{sites[boundary.conversion_site]}' and '{boundary.name}'"
            )
        else:
            sites[boundary.conversion_site] = boundary.name

        if not boundary.crossings:
            violations.append(f"boundary '{boundary.name}' declares no unit crossing")
        for crossing in boundary.crossings:
            if crossing.conversion not in CONVERSION_NAMES:
                violations.append(
                    f"boundary '{boundary.name}' names undeclared conversion "
                    f"'{crossing.conversion}'"
                )
            for unit in (crossing.source_unit, crossing.target_unit):
                if unit not in TAG_TYPE_NAMES:
                    violations.append(
                        f"boundary '{boundary.name}' crossing names undeclared unit '{unit}'"
                    )

    return tuple(violations)
