"""The unit-file parser preserves the two systemd semantics a naive split would drop.

These are the properties `staticcheck` depends on: repeated list directives append, an empty
assignment resets, and scalar directives take the last value. If any of these were wrong the
sandbox checks would read the wrong family set and pass a unit they should reject.
"""

from __future__ import annotations

from ops.acl.unitfile import parse_unit


def test_sections_and_scalar_last_wins() -> None:
    """Sections are separated and a repeated scalar directive takes the final value."""
    unit = parse_unit(
        "[Unit]\nDescription=first\n[Service]\nProtectSystem=full\nProtectSystem=strict\n"
    )
    assert unit.scalar("Unit", "Description") == "first"
    assert unit.scalar("Service", "ProtectSystem") == "strict"
    assert unit.has("Service", "ProtectSystem")
    assert not unit.has("Service", "User")


def test_list_directive_appends_across_repeats() -> None:
    """Repeated list directives accumulate rather than overwrite (systemd append semantics)."""
    unit = parse_unit("[Service]\nReadWritePaths=/run/lock\nReadWritePaths=/var/log/openarm\n")
    assert unit.values("Service", "ReadWritePaths") == ["/run/lock", "/var/log/openarm"]


def test_empty_assignment_resets_the_list() -> None:
    """An empty assignment clears the accumulated list rather than adding a blank entry."""
    unit = parse_unit(
        "[Service]\n"
        "RestrictAddressFamilies=AF_INET AF_INET6\n"
        "RestrictAddressFamilies=\n"
        "RestrictAddressFamilies=AF_CAN\n"
    )
    assert unit.values("Service", "RestrictAddressFamilies") == ["AF_CAN"]
    # Present even though it was reset mid-way — the author addressed the directive.
    assert unit.has("Service", "RestrictAddressFamilies")


def test_comments_and_continuations() -> None:
    """Comment lines are ignored and backslash continuations fold into one logical line."""
    unit = parse_unit(
        "[Service]\n# a comment\n; another comment\nDeviceAllow=/dev/null rw \\\n  char-ttyACM rw\n"
    )
    values = unit.values("Service", "DeviceAllow")
    assert len(values) == 1  # the two physical lines folded into one logical directive
    assert "/dev/null rw" in values[0]
    assert "char-ttyACM rw" in values[0]
