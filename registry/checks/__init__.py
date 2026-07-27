"""The rule roster: every executable in `06` §5, in rule order.

`02a` §−2.3 makes the roster itself a contract. This work package owns the
executables and not the rules, so adding a check that `06` §5 does not contain is
a violation, and so is omitting one it does.

Two ranges, and the difference between them is deliberate — `02a` §−2.3 explicitly
warns against "correcting" the two numbers to match:

* `BUILD_RANGE` — `CI-01`..`CI-18`. Every rule in `06` §5 has an executable.
* `JUDGE_RANGE` — `BUILD_RANGE` minus `JUDGE_EXCLUDED`. What the BOOT band's own
  acceptance is decided by.

One rule is excluded:

* `CI-18` — **permanent.** Its predicate cites this very acceptance gate, so
  judging it would make the gate reference itself.

`CI-07` was excluded on the same circularity while Wave −1 could not run until this
gate passed, on the stated condition that the exclusion be lifted once Wave −1 landed.
Wave −1 has landed, so it is judged. It did not go green on its own: `02a`'s `NORM-*`
table names requirements as contested that `docs/v1/plan/normalization/ledger.yaml`
carries no structured ruling for, and the seeder stamps the hash only from the
structured winners — deliberately, because stamping from the same free-text columns
`CI-07` reads would make the rule green while catching nothing. The gap between the two
is unruled contested requirements, which is what `CI-07` exists to report. Keeping the
exclusion past its condition would have left a rule that is present in the code and
switched off in the config, which is the shape that gets trusted without being true.
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

# Rules whose predicate references the band gate's own pass/fail state, and which
# therefore receive the running judged-finding tally as a second argument.
GATE_STATE_RULES = ("CI-18",)

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
