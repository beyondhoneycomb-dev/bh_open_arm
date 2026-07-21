"""Audit torque never reaches a training action target (WP-0A-02).

Acceptance ③: gravity or safety torque supplied to a position action target is
statically rejected. Safety and gravity torque are separate execution and audit
channels; the position action is the training target, so a torque there would
teach a policy to imitate a safety intervention (00 §8.3). This exercises the AST
checker over a fixture that sneaks a torque in, and confirms a clean position
target is not over-flagged.

It also asserts the schema-level half of the same separation: `executedMitCommand`
and `safetyOverride` are audit-only and can never be the training target.
"""

from __future__ import annotations

from pathlib import Path

from contracts.action import (
    RULE_TORQUE_IN_ACTION_TARGET,
    TRAINING_TARGET_CHANNEL,
    check_action_target_source,
    is_audit_only,
    load_schema,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _source(name: str) -> str:
    """Return a fixture file's source text."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_gravity_torque_in_action_target_is_flagged() -> None:
    """A torque flowing into the action target is a static-checker violation."""
    findings = check_action_target_source(_source("checker_gravity_torque_sneak.py"))
    assert findings
    assert findings[0].rule == RULE_TORQUE_IN_ACTION_TARGET


def test_clean_position_target_is_not_flagged() -> None:
    """A position-only action target is not flagged (no over-blocking)."""
    assert check_action_target_source(_source("checker_clean.py")) == ()


def test_direct_nm_construction_is_flagged() -> None:
    """Constructing an action target directly from an Nm value is flagged."""
    source = (
        "from contracts.action import AcceptedPositionAction\n"
        "from contracts.units import Nm\n"
        "x = AcceptedPositionAction(values=(Nm(1.0),))\n"
    )
    assert check_action_target_source(source)


def test_mit_command_is_audit_only() -> None:
    """The executed MIT command may never be the training target."""
    schema = load_schema()
    assert is_audit_only(schema, "executedMitCommand")
    assert schema.training_target_channel != "executedMitCommand"


def test_safety_override_is_audit_only() -> None:
    """The safety metadata may never be the training target."""
    assert is_audit_only(load_schema(), "safetyOverride")


def test_training_target_is_the_accepted_position() -> None:
    """The sole training target is the post-clamp position action."""
    assert TRAINING_TARGET_CHANNEL == "acceptedPositionAction"
    assert load_schema().training_target_channel == "acceptedPositionAction"
