"""The rule roster: every executable in `06` §5, in rule order.

`02a` §−2.3 makes the roster itself a contract. This work package owns the
executables and not the rules, so adding a check that `06` §5 does not contain is
a violation, and so is omitting one it does.

Two ranges, and the difference between them is deliberate — `02a` §−2.3 explicitly
warns against "correcting" the two numbers to match:

* `BUILD_RANGE` — `CI-01`..`CI-18`. Every rule in `06` §5 has an executable.
* `JUDGE_RANGE` — `CI-01`..`CI-17`. What the BOOT band's own acceptance is decided
  by. `CI-18` is excluded because its predicate cites that very acceptance gate,
  so including it would make the gate reference itself.
"""

from __future__ import annotations

from types import ModuleType

from registry.checks import (
    ci_01,
    ci_01b,
    ci_02,
    ci_02b,
    ci_03,
    ci_03b,
    ci_03c,
    ci_03d,
    ci_04,
    ci_04b,
    ci_04c,
    ci_04d,
    ci_05,
    ci_05b,
    ci_05c,
    ci_05d,
    ci_05e,
    ci_06,
    ci_07,
    ci_08,
    ci_09,
    ci_10,
    ci_11,
    ci_11b,
    ci_11b_self,
    ci_11c,
    ci_12,
    ci_13,
    ci_14,
    ci_14b,
    ci_14c,
    ci_15,
    ci_16,
    ci_17,
    ci_18,
)

BUILD_RANGE: tuple[ModuleType, ...] = (
    ci_01,
    ci_01b,
    ci_02,
    ci_02b,
    ci_03,
    ci_03b,
    ci_03c,
    ci_03d,
    ci_04,
    ci_04b,
    ci_04c,
    ci_04d,
    ci_05,
    ci_05b,
    ci_05c,
    ci_05d,
    ci_05e,
    ci_06,
    ci_07,
    ci_08,
    ci_09,
    ci_10,
    ci_11,
    ci_11b,
    ci_11b_self,
    ci_11c,
    ci_12,
    ci_13,
    ci_14,
    ci_14b,
    ci_14c,
    ci_15,
    ci_16,
    ci_17,
    ci_18,
)

JUDGE_EXCLUDED = ("CI-18",)

JUDGE_RANGE: tuple[ModuleType, ...] = tuple(
    module for module in BUILD_RANGE if module.RULE_ID not in JUDGE_EXCLUDED
)

RULE_IDS: tuple[str, ...] = tuple(module.RULE_ID for module in BUILD_RANGE)


def module_for(rule_id: str) -> ModuleType:
    """Look up the executable for a rule id.

    Args:
        rule_id: A `CI-*` identifier.

    Returns:
        (ModuleType) The module implementing that rule.

    Raises:
        KeyError: When no executable exists for the id.
    """
    for module in BUILD_RANGE:
        if rule_id == module.RULE_ID:
            return module
    raise KeyError(f"no executable for rule {rule_id}")
