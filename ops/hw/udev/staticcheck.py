"""Static checks over stored udev rule text — the two invariants a generator alone cannot guarantee.

`build_rule` guarantees a rule *it* produces is two-axis and non-`can`-prefixed. It
cannot vouch for a `.rules` file edited by hand or produced elsewhere, so before any
such file is stored it is scanned:

- **`can`-prefix ban** (`01` FR-SYS-008, acceptance ⑦) — a `NAME="can…"` value races
  the kernel's `canN` assignment; `find_can_prefixed_names` flags every occurrence.
- **Two-axis requirement** (`01` FR-SYS-008, contract "1축 규칙 → 저장 거부") — a fixed-name
  rule must constrain both an adapter axis (`ATTRS{serial}` or `KERNELS`) and the
  channel axis (`ATTR{dev_id}`); `find_single_axis_rules` flags any that constrain
  fewer than both.

Both scans read the rule *text*, because that is the artifact that gets installed and
the exact thing the acceptance fixtures are.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ops.hw.udev.rules import BANNED_NAME_PREFIX

# A `NAME="..."` assignment (single `=`), distinct from the `KEY=="..."` match tests.
_NAME_ASSIGN = re.compile(r'NAME="([^"]*)"')
# The adapter-axis match keys and the channel-axis match key, as they appear in a rule.
_SERIAL_AXIS = re.compile(r"ATTRS\{serial\}==")
_PORT_PATH_AXIS = re.compile(r"KERNELS==")
_DEV_ID_AXIS = re.compile(r"ATTR\{dev_id\}==")


@dataclass(frozen=True)
class RuleViolation:
    """A rejected udev rule line.

    Attributes:
        line: 1-indexed line number within the scanned text.
        rule_line: The offending rule line, stripped.
        reason: Why it is rejected, for the report.
    """

    line: int
    rule_line: str
    reason: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.reason}: {self.rule_line}"


def _rule_lines(text: str) -> list[tuple[int, str]]:
    """Return the non-comment, non-blank lines of a rules file with 1-indexed numbers.

    Continuation backslashes are folded so a rule split across physical lines is
    scanned as the single logical rule udev sees.

    Args:
        text: Rules file body.

    Returns:
        (list[tuple[int, str]]) `(line_number, logical_rule)` pairs.
    """
    logical: list[tuple[int, str]] = []
    pending = ""
    start_line = 0
    for index, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            continue
        if not pending:
            start_line = index
        if stripped.endswith("\\"):
            pending += stripped[:-1].strip() + " "
            continue
        pending += stripped
        logical.append((start_line, pending.strip()))
        pending = ""
    if pending:
        logical.append((start_line, pending.strip()))
    return logical


def find_can_prefixed_names(text: str) -> list[RuleViolation]:
    """Flag every rule whose `NAME=` value starts with `can` (acceptance ⑦).

    Args:
        text: Rules file body.

    Returns:
        (list[RuleViolation]) One per `can`-prefixed name, in file order.
    """
    violations: list[RuleViolation] = []
    for number, line in _rule_lines(text):
        for match in _NAME_ASSIGN.finditer(line):
            if match.group(1).startswith(BANNED_NAME_PREFIX):
                violations.append(
                    RuleViolation(
                        line=number,
                        rule_line=line,
                        reason=f"fixed name {match.group(1)!r} starts with {BANNED_NAME_PREFIX!r}",
                    )
                )
    return violations


def find_single_axis_rules(text: str) -> list[RuleViolation]:
    """Flag every fixed-name rule that does not constrain both axes (store guard).

    A rule that assigns a `NAME=` must carry an adapter axis (`ATTRS{serial}` or
    `KERNELS`) and the channel axis (`ATTR{dev_id}`). Missing either → rejected.

    Args:
        text: Rules file body.

    Returns:
        (list[RuleViolation]) One per single-axis (or zero-axis) named rule.
    """
    violations: list[RuleViolation] = []
    for number, line in _rule_lines(text):
        if not _NAME_ASSIGN.search(line):
            continue
        has_adapter = bool(_SERIAL_AXIS.search(line) or _PORT_PATH_AXIS.search(line))
        has_channel = bool(_DEV_ID_AXIS.search(line))
        if has_adapter and has_channel:
            continue
        missing = []
        if not has_adapter:
            missing.append("adapter axis (ATTRS{serial} or KERNELS)")
        if not has_channel:
            missing.append("channel axis (ATTR{dev_id})")
        violations.append(
            RuleViolation(
                line=number,
                rule_line=line,
                reason="rule is not two-axis; missing " + " and ".join(missing),
            )
        )
    return violations
