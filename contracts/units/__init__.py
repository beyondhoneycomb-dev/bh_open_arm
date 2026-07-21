"""CTR-UNIT@v1 — frozen unit tag types and their only conversion paths.

The public surface of the unit-safety contract. Consumers import tag types and
named conversions from here; crossing between units is possible only through the
conversion functions, and the boundary table plus static checker enforce that each
crossing happens at exactly one declared site.
"""

from __future__ import annotations

from contracts.units.boundary import (
    CONTRACT_PATH,
    REQUIRED_BOUNDARIES,
    Boundary,
    BoundaryTable,
    Crossing,
    load_boundary_table,
    parse_boundary_table,
    validate_boundary_table,
)
from contracts.units.checker import (
    RULE_BARE_FLOAT,
    RULE_IMPLICIT_RECONSTRUCTION,
    RULE_UNDECLARED_BOUNDARY,
    Violation,
    check_source,
)
from contracts.units.conversions import (
    deg_per_sec_to_rad_per_sec,
    deg_to_rad,
    rad_per_sec_to_deg_per_sec,
    rad_to_deg,
)
from contracts.units.observation import (
    ObservationChannel,
    expected_dim,
    observation_state_units,
)
from contracts.units.tags import (
    Deg,
    DegPerSec,
    Nm,
    PacketTorque,
    Rad,
    RadPerSec,
)
from contracts.units.torque import (
    clamp_torque,
    nm_to_packet,
    packet_to_nm,
)

__all__ = [
    "CONTRACT_PATH",
    "REQUIRED_BOUNDARIES",
    "RULE_BARE_FLOAT",
    "RULE_IMPLICIT_RECONSTRUCTION",
    "RULE_UNDECLARED_BOUNDARY",
    "Boundary",
    "BoundaryTable",
    "Crossing",
    "Deg",
    "DegPerSec",
    "Nm",
    "ObservationChannel",
    "PacketTorque",
    "Rad",
    "RadPerSec",
    "Violation",
    "check_source",
    "clamp_torque",
    "deg_per_sec_to_rad_per_sec",
    "deg_to_rad",
    "expected_dim",
    "load_boundary_table",
    "nm_to_packet",
    "observation_state_units",
    "packet_to_nm",
    "parse_boundary_table",
    "rad_per_sec_to_deg_per_sec",
    "rad_to_deg",
    "validate_boundary_table",
]
