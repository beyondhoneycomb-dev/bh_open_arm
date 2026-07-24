"""Static scans that hold WP-3C-07's two structural invariants in the source itself.

Two of WP-3C-07's rules are properties of the *code*, not just of a run, and a static
scan is what keeps them from eroding as the package changes:

- **No re-stamp on resume (⑤).** The resume path must reuse the existing stamped
  `repo_id`; calling `stamp_repo_id()` anywhere in this package would mint a divergent
  name. The scan flags any call to it.
- **No auto-save on recovery (③).** The recovery and choice paths must present a
  save/discard choice, never accept the episode automatically. The scan flags any call
  that would save or accept an episode — `save_episode`, or the `EpisodeLabel`
  constructors/mutators that produce accepted, auto-saved data (`judged`, `suggested`,
  `with_manual`, `with_auto`).

The scan is AST-based, so a forbidden name written in a docstring or a string constant
(as this module's own sets are) is not a call and is not flagged — only an actual
invocation is. The runtime tests assert the same two properties on a live run; this is
the half that bites before the code ever runs.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# Calling `stamp_repo_id` re-derives the session name — the WP-3C-07 ⑤ divergence.
RESTAMP_CALLS = frozenset({"stamp_repo_id"})

# Calls that save or accept an episode as data. None may appear on the automatic crash
# path: a recovered episode is presented for judgment, never auto-saved (WP-3C-07 ③).
AUTO_SAVE_CALLS = frozenset({"save_episode", "judged", "suggested", "with_manual", "with_auto"})

RULE_NO_RESTAMP = "no-restamp"
RULE_NO_AUTO_SAVE = "no-auto-save"

_PYTHON_SUFFIX = ".py"


@dataclass(frozen=True)
class StaticViolation:
    """One forbidden call found by a static scan.

    Attributes:
        filename: The file the call was found in.
        line: The 1-indexed line of the call.
        symbol: The called name.
        rule: Which invariant it breaks (`no-restamp` or `no-auto-save`).
    """

    filename: str
    line: int
    symbol: str
    rule: str


def _rule_for(symbol: str) -> str | None:
    """Return the rule a called symbol breaks, or None when it is allowed."""
    if symbol in RESTAMP_CALLS:
        return RULE_NO_RESTAMP
    if symbol in AUTO_SAVE_CALLS:
        return RULE_NO_AUTO_SAVE
    return None


def _called_symbol(node: ast.Call) -> str | None:
    """The bare name a call targets — `f()` -> "f", `x.f()` -> "f", else None."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def scan_source(source: str, filename: str) -> tuple[StaticViolation, ...]:
    """Scan one Python source string for forbidden calls.

    Args:
        source: The Python source text.
        filename: The name to attribute violations to.

    Returns:
        (tuple[StaticViolation, ...]) One violation per forbidden call, in source order.

    Raises:
        SyntaxError: When the source does not parse.
    """
    tree = ast.parse(source, filename=filename)
    violations: list[StaticViolation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        symbol = _called_symbol(node)
        if symbol is None:
            continue
        rule = _rule_for(symbol)
        if rule is None:
            continue
        violations.append(
            StaticViolation(filename=filename, line=node.lineno, symbol=symbol, rule=rule)
        )
    return tuple(violations)


def scan_tree(root: Path) -> tuple[StaticViolation, ...]:
    """Scan every Python file under a directory for forbidden calls.

    Args:
        root: The directory to scan (the crash-recovery package).

    Returns:
        (tuple[StaticViolation, ...]) Every violation found, ordered by file then line.
    """
    violations: list[StaticViolation] = []
    for path in sorted(root.rglob(f"*{_PYTHON_SUFFIX}")):
        violations.extend(scan_source(path.read_text(encoding="utf-8"), str(path)))
    return tuple(violations)
