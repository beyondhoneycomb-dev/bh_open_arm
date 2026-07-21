"""The rad-deg boundary table: full coverage, one site per boundary (WP-0A-04).

Acceptance items 4 and 5: the table must cover every named rad-deg boundary, and a
boundary must own exactly one conversion site — two sites for one boundary is the
double-conversion bug and is rejected.
"""

from __future__ import annotations

from typing import Any

from contracts.units import REQUIRED_BOUNDARIES, load_boundary_table, validate_boundary_table
from contracts.units.boundary import parse_boundary_table


def _one_crossing(conversion: str = "deg_to_rad") -> list[dict[str, str]]:
    """Return a minimal valid crossing list for a fixture boundary."""
    return [{"conversion": conversion, "from": "Deg", "to": "Rad"}]


def _full_document() -> dict[str, Any]:
    """Return an in-memory table that covers every required boundary once."""
    return {
        "boundaries": [
            {
                "boundary": name,
                "conversion_site": f"site.for.{index}",
                "crossings": _one_crossing(),
            }
            for index, name in enumerate(REQUIRED_BOUNDARIES)
        ]
    }


def test_frozen_contract_table_is_valid() -> None:
    """The shipped contracts/unit_tags.yaml validates with no violations."""
    assert validate_boundary_table(load_boundary_table()) == ()


def test_frozen_contract_covers_every_required_boundary() -> None:
    """Each named rad-deg boundary appears in the shipped table."""
    names = {boundary.name for boundary in load_boundary_table().boundaries}
    assert set(REQUIRED_BOUNDARIES) <= names


def test_frozen_contract_has_one_site_per_boundary() -> None:
    """Every boundary owns exactly one non-empty, unique conversion site."""
    boundaries = load_boundary_table().boundaries
    sites = [boundary.conversion_site for boundary in boundaries]
    assert all(sites), "a boundary declared no conversion site"
    assert len(sites) == len(set(sites)), "a conversion site is shared across boundaries"


def test_missing_boundary_is_rejected() -> None:
    """Dropping a required boundary is a coverage violation (acceptance 4)."""
    document = _full_document()
    document["boundaries"] = document["boundaries"][:-1]
    violations = validate_boundary_table(parse_boundary_table(document))
    assert any("required boundary" in message for message in violations)


def test_two_sites_for_one_boundary_is_rejected() -> None:
    """A boundary declared twice is two sites for one boundary (acceptance 5)."""
    document = _full_document()
    duplicate = dict(document["boundaries"][0])
    duplicate["conversion_site"] = "site.second.copy"
    document["boundaries"].append(duplicate)
    violations = validate_boundary_table(parse_boundary_table(document))
    assert any("declared 2 times" in message for message in violations)


def test_shared_site_across_boundaries_is_rejected() -> None:
    """One site owning two boundaries collapses the single-owner invariant."""
    document = _full_document()
    document["boundaries"][1]["conversion_site"] = document["boundaries"][0]["conversion_site"]
    violations = validate_boundary_table(parse_boundary_table(document))
    assert any("is shared by boundaries" in message for message in violations)


def test_undeclared_conversion_name_is_rejected() -> None:
    """A crossing naming an unknown conversion function is rejected."""
    document = _full_document()
    document["boundaries"][0]["crossings"] = _one_crossing(conversion="deg_to_furlong")
    violations = validate_boundary_table(parse_boundary_table(document))
    assert any("undeclared conversion" in message for message in violations)
