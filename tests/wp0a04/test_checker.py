"""The AST static checker: bare floats, undeclared boundaries, unit sneaks.

Covers the acceptance items the type system alone cannot express:
- 6: a physical quantity declared as a bare float is rejected.
- 4: a conversion called outside its one sanctioned site is rejected.
- 3: reconstructing a unit from a foreign `.value` is rejected.

Each rule is exercised with both a violating source and a clean one, so the
checker is shown to reject the fault without punishing honest code.
"""

from __future__ import annotations

from contracts.units import (
    RULE_BARE_FLOAT,
    RULE_IMPLICIT_RECONSTRUCTION,
    RULE_UNDECLARED_BOUNDARY,
    check_source,
)

ALLOWED = ["m.approved_site"]


def _rules(source: str) -> set[str]:
    """Return the set of rule ids the checker fires on a source string."""
    return {violation.rule for violation in check_source(source, ALLOWED, module="m")}


def test_bare_float_physical_quantity_is_flagged() -> None:
    """A physically-named parameter typed as bare float is rejected (acceptance 6)."""
    source = "def send(joint_angle: float) -> None:\n    return None\n"
    assert RULE_BARE_FLOAT in _rules(source)


def test_bare_float_container_is_flagged() -> None:
    """A bare list[float] of a physical quantity is rejected too."""
    source = "def send(joint_positions: list[float]) -> None:\n    return None\n"
    assert RULE_BARE_FLOAT in _rules(source)


def test_dimensionless_float_is_not_flagged() -> None:
    """A genuinely dimensionless float (a scale factor) is not flagged."""
    source = "def scale(factor: float) -> float:\n    return factor * 2.0\n"
    assert RULE_BARE_FLOAT not in _rules(source)


def test_tag_typed_parameter_is_not_flagged() -> None:
    """A physical quantity given a tag type is accepted."""
    source = (
        "from contracts.units import Deg\ndef send(joint_angle: Deg) -> None:\n    return None\n"
    )
    assert RULE_BARE_FLOAT not in _rules(source)


def test_conversion_outside_declared_site_is_flagged() -> None:
    """A conversion called anywhere but its site is an undeclared boundary (4)."""
    source = "from contracts.units import deg_to_rad\ndef rogue(x):\n    return deg_to_rad(x)\n"
    assert RULE_UNDECLARED_BOUNDARY in _rules(source)


def test_conversion_at_module_level_is_flagged() -> None:
    """A conversion outside any function has no owning site and is flagged."""
    source = "from contracts.units import deg_to_rad, Deg\nvalue = deg_to_rad(Deg(1.0))\n"
    assert RULE_UNDECLARED_BOUNDARY in _rules(source)


def test_conversion_inside_declared_site_is_allowed() -> None:
    """A conversion inside its sanctioned site is not flagged."""
    source = (
        "from contracts.units import deg_to_rad\ndef approved_site(x):\n    return deg_to_rad(x)\n"
    )
    assert RULE_UNDECLARED_BOUNDARY not in _rules(source)


def test_reconstruction_from_value_is_flagged() -> None:
    """Rebuilding a unit from a foreign .value bypasses conversion (acceptance 3)."""
    source = "from contracts.units import Rad\ndef rogue(deg):\n    return Rad(deg.value)\n"
    assert RULE_IMPLICIT_RECONSTRUCTION in _rules(source)


def test_reconstruction_inside_declared_site_is_allowed() -> None:
    """The sanctioned site may touch raw values to perform the crossing."""
    source = "from contracts.units import Rad\ndef approved_site(deg):\n    return Rad(deg.value)\n"
    assert RULE_IMPLICIT_RECONSTRUCTION not in _rules(source)


def test_plain_construction_is_not_flagged() -> None:
    """Constructing a unit from a literal is normal and not a sneak."""
    source = "from contracts.units import Deg\nangle = Deg(90.0)\n"
    assert RULE_IMPLICIT_RECONSTRUCTION not in _rules(source)
