"""Static check: no torque may reach a position action target (acceptance ③).

The type system already stops the plain case — an action target is typed `Deg`, so
handing it an `Nm` fails to type-check. This checker catches the same intent
expressed through source shapes a type error message would describe obscurely: a
gravity or safety torque, or any `Nm` / `PacketTorque` value, flowing into the
construction of an action-target channel. Keeping the domain rule as its own check
gives a message that names the actual contract violation ("torque in an action
target") and lets the fixture corpus prove the rule bites.

Safety and gravity torque are separate execution and audit channels; letting them
into `requestedPositionAction` / `acceptedPositionAction` is exactly the leak
00 §8.3 forbids, because the position action is the training target.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

RULE_TORQUE_IN_ACTION_TARGET = "torque-in-action-target"

# The action-target channel constructors; a torque argument to either is the leak.
ACTION_TARGET_TYPES = ("RequestedPositionAction", "AcceptedPositionAction")

# Tag types that carry torque. A physical torque or a raw packet torque handed to
# a position action is the violation.
_TORQUE_TYPE_NAMES = ("Nm", "PacketTorque")

# Identifier fragments that mark a value as a torque, including the gravity and
# safety components the contract keeps out of the action path.
_TORQUE_NAME_TOKENS = ("torque", "tau", "gravity", "effort")


@dataclass(frozen=True)
class Violation:
    """One static-checker finding.

    Attributes:
        rule: Which rule fired.
        module: Dotted module path of the checked source.
        line: 1-indexed source line.
        message: Human-readable description of the violation.
    """

    rule: str
    module: str
    line: int
    message: str


def check_action_target_source(source: str, module: str = "<source>") -> tuple[Violation, ...]:
    """Flag torque values flowing into an action-target constructor.

    Args:
        source: Python source to analyse.
        module: Dotted module path used in findings.

    Returns:
        (tuple[Violation, ...]) Findings in source order; empty when clean.
    """
    tree = ast.parse(source)
    findings: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _called_name(node) not in ACTION_TARGET_TYPES:
            continue
        arguments = list(node.args) + [keyword.value for keyword in node.keywords]
        if any(_is_torque_bearing(argument) for argument in arguments):
            findings.append(
                Violation(
                    rule=RULE_TORQUE_IN_ACTION_TARGET,
                    module=module,
                    line=node.lineno,
                    message=(
                        f"torque supplied to action target '{_called_name(node)}'; safety and "
                        f"gravity torque are separate audit channels, never a training target "
                        f"(00 §8.3)"
                    ),
                )
            )
    return tuple(findings)


def _called_name(call: ast.Call) -> str | None:
    """Return the simple name of a call target, or None."""
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _identifier(node: ast.expr) -> str | None:
    """Return the simple identifier of a name or attribute expression, or None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_torque_bearing(node: ast.expr) -> bool:
    """Report whether an expression carries a torque, recursing into sequences.

    Args:
        node: The argument expression to test.

    Returns:
        (bool) True when the expression is a torque tag construction, a
        torque-named identifier, or a sequence literal containing one.
    """
    if isinstance(node, ast.Call) and _called_name(node) in _TORQUE_TYPE_NAMES:
        return True
    identifier = _identifier(node)
    if identifier is not None and any(token in identifier.lower() for token in _TORQUE_NAME_TOKENS):
        return True
    if isinstance(node, ast.Tuple | ast.List):
        return any(_is_torque_bearing(element) for element in node.elts)
    return False
