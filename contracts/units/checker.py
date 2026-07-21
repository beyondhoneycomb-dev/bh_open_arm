"""Static checks that the type system alone cannot express.

The tag types stop the errors a type checker can see: a wrong-unit assignment, a
mixed-unit sum. Three failures survive that net, and this module catches them by
reading source as an AST:

- A physical quantity declared as a bare `float` (or a bare float container). The
  type checker cannot object to `float` where no tag type was ever written; this
  rule refuses to let a quantity be born untyped (`SPINE` §2-7, acceptance 6).
- A conversion called anywhere but its one sanctioned site. `contracts.units`
  conversions may run only inside the function the boundary table names for that
  boundary; a call elsewhere is a conversion at an undeclared boundary
  (acceptance 4).
- A tag type reconstructed from another value's raw `.value`, e.g. `Rad(x.value)`.
  That unwraps a quantity and re-wraps it in a different unit with no conversion —
  the exact 57.3x bug the named conversions exist to prevent (acceptance 3).

The checker takes the sanctioned sites explicitly rather than importing the table,
so it can be pointed at any source tree and any allowlist, and so a test can
exercise it without a file on disk.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass

from contracts.units.boundary import CONVERSION_NAMES, TAG_TYPE_NAMES

RULE_BARE_FLOAT = "bare-float-physical-quantity"
RULE_UNDECLARED_BOUNDARY = "conversion-at-undeclared-boundary"
RULE_IMPLICIT_RECONSTRUCTION = "implicit-unit-reconstruction"

# Name fragments that mark an identifier as carrying a physical quantity. A bare
# `float` on a parameter named from this set is the untyped-quantity smell; a
# `float` named `factor` or `scale` is dimensionless and deliberately not flagged,
# so the rule does not punish honest scalars (no over-blocking).
PHYSICAL_QUANTITY_TOKENS = (
    "pos",
    "position",
    "angle",
    "deg",
    "rad",
    "vel",
    "velocity",
    "torque",
    "tau",
    "effort",
    "joint",
    "gripper",
)

# Bare float annotation forms, space- and case-normalised. A physical quantity
# wearing any of these has no tag type and is rejected.
_BARE_FLOAT_FORMS = frozenset(
    {
        "float",
        "list[float]",
        "tuple[float]",
        "tuple[float,...]",
        "sequence[float]",
        "iterable[float]",
    }
)

# The wrapper field every tag type exposes; reconstructing a unit from a foreign
# `.value` is the implicit-conversion bypass this checker refuses.
_WRAPPER_FIELD = "value"


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


def check_source(
    source: str, allowed_sites: Iterable[str], module: str = "<source>"
) -> tuple[Violation, ...]:
    """Run every static unit check over one source string.

    Args:
        source: Python source to analyse.
        allowed_sites: Fully-qualified function names sanctioned to perform
            conversions (the boundary table's conversion sites).
        module: Dotted module path used to build enclosing-function qualnames, so
            they can be compared against `allowed_sites`.

    Returns:
        (tuple[Violation, ...]) All findings, in source order.
    """
    tree = ast.parse(source)
    sites = frozenset(allowed_sites)
    findings: list[Violation] = []
    findings.extend(_check_bare_float(tree, module))
    findings.extend(_check_conversions(tree, module, sites))
    findings.extend(_check_reconstruction(tree, module, sites))
    return tuple(sorted(findings, key=lambda finding: (finding.line, finding.rule)))


def _is_physical_name(name: str) -> bool:
    """Return whether an identifier names a physical quantity."""
    lowered = name.lower()
    return any(token in lowered for token in PHYSICAL_QUANTITY_TOKENS)


def _is_bare_float(annotation: ast.expr | None) -> bool:
    """Return whether an annotation is a bare float or bare float container."""
    if annotation is None:
        return False
    normalised = ast.unparse(annotation).replace(" ", "").lower()
    return normalised in _BARE_FLOAT_FORMS


def _check_bare_float(tree: ast.AST, module: str) -> list[Violation]:
    """Flag physical quantities declared as bare floats (acceptance 6)."""
    findings: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        arguments = [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]
        if node.args.vararg is not None:
            arguments.append(node.args.vararg)
        if node.args.kwarg is not None:
            arguments.append(node.args.kwarg)
        for argument in arguments:
            if _is_physical_name(argument.arg) and _is_bare_float(argument.annotation):
                findings.append(
                    Violation(
                        rule=RULE_BARE_FLOAT,
                        module=module,
                        line=argument.lineno,
                        message=(
                            f"parameter '{argument.arg}' carries a physical quantity as a bare "
                            f"float; declare it with a unit tag type"
                        ),
                    )
                )
        if _is_physical_name(node.name) and _is_bare_float(node.returns):
            findings.append(
                Violation(
                    rule=RULE_BARE_FLOAT,
                    module=module,
                    line=node.lineno,
                    message=(
                        f"function '{node.name}' returns a physical quantity as a bare float; "
                        f"declare its return with a unit tag type"
                    ),
                )
            )
    return findings


def _called_name(call: ast.Call) -> str | None:
    """Return the simple name of a call target, or None."""
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _scoped_calls(tree: ast.AST, module: str) -> list[tuple[ast.Call, str | None]]:
    """Return every call paired with the qualname of its enclosing function.

    The qualname is `module` plus the chain of enclosing function and class names.
    A call at module level has no enclosing function and is paired with None.
    """
    calls: list[tuple[ast.Call, str | None]] = []

    def recurse(node: ast.AST, scope: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                recurse(child, (*scope, child.name))
                continue
            if isinstance(child, ast.Call):
                qualname = f"{module}." + ".".join(scope) if scope else None
                calls.append((child, qualname))
            recurse(child, scope)

    recurse(tree, ())
    return calls


def _check_conversions(tree: ast.AST, module: str, sites: frozenset[str]) -> list[Violation]:
    """Flag conversion calls outside a sanctioned site (acceptance 4)."""
    findings: list[Violation] = []
    for call, qualname in _scoped_calls(tree, module):
        name = _called_name(call)
        if name not in CONVERSION_NAMES:
            continue
        if qualname is None or qualname not in sites:
            location = qualname or f"{module}:<module-level>"
            findings.append(
                Violation(
                    rule=RULE_UNDECLARED_BOUNDARY,
                    module=module,
                    line=call.lineno,
                    message=(
                        f"conversion '{name}' called at '{location}', which the boundary table "
                        f"does not declare as a conversion site"
                    ),
                )
            )
    return findings


def _check_reconstruction(tree: ast.AST, module: str, sites: frozenset[str]) -> list[Violation]:
    """Flag `Unit(x.value)` reconstruction outside a sanctioned site (acceptance 3)."""
    findings: list[Violation] = []
    for call, qualname in _scoped_calls(tree, module):
        name = _called_name(call)
        if name not in TAG_TYPE_NAMES:
            continue
        unwraps = any(
            isinstance(argument, ast.Attribute) and argument.attr == _WRAPPER_FIELD
            for argument in call.args
        )
        if unwraps and (qualname is None or qualname not in sites):
            findings.append(
                Violation(
                    rule=RULE_IMPLICIT_RECONSTRUCTION,
                    module=module,
                    line=call.lineno,
                    message=(
                        f"'{name}' reconstructed from a raw .value; cross units through a named "
                        f"conversion, not by unwrapping"
                    ),
                )
            )
    return findings
