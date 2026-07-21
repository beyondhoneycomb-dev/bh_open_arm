"""Static checks the dummy package must pass (acceptance ③ static, ⑤, ⑥).

Three source-level bans, enforced by AST rather than grep so a symbol used in a
comment or string does not trip them and a symbol used for real cannot hide behind
formatting:

- **No LeRobot in-tree loop import (⑤, 01 FR-SYS-003).** The teleop/record/inference
  loops live in `lerobot.scripts.*` (`lerobot_teleoperate.py`, `lerobot_record.py`,
  …), and the plan owns those loops itself rather than driving LeRobot's. Importing
  anything under `lerobot.scripts` is pulling an in-tree loop. Importing the LeRobot
  ABCs (`lerobot.robots`, `lerobot.teleoperators`) is fine and expected — those are
  the plugin surface, not a loop.
- **No CLI subprocess spawn (⑥, 01 FR-SYS-002).** No `subprocess`, no `os.system` /
  `os.popen` / `os.exec*` / `os.spawn*` / `os.posix_spawn*`, no `pty.spawn`. The
  dummy is an in-process device; spawning a CLI is how the banned "shell out to a
  LeRobot script" pattern re-enters.
- **No CAN symbol (③ static, 09 FR-SIM-098).** No `import can`, no `AF_CAN` /
  `PF_CAN` / `CAN_RAW` family constants. The runtime `canguard` proves the same at
  execution time; this proves it before the code ever runs.

`check_package` walks a package's `.py` files and returns every violation; the
acceptance test runs it over this package and asserts zero, and over inline
fixtures that each contain one banned form to prove the checks bite.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

RULE_INTREE_LOOP_IMPORT = "lerobot-intree-loop-import"
RULE_CLI_SPAWN = "cli-subprocess-spawn"
RULE_CAN_SYMBOL = "can-symbol"

# The in-tree loop/CLI package. Every teleop/record/inference loop LeRobot ships
# lives beneath it; the ABCs the plugin subclasses do not.
_INTREE_LOOP_PREFIX = "lerobot.scripts"

# Module roots whose import is a subprocess spawn on its own.
_SPAWN_MODULES = frozenset({"subprocess"})

# `os` functions that spawn a process, and `pty.spawn`. Flagged whether reached via
# attribute (`os.system(...)`) or direct import (`from os import system`).
_OS_SPAWN_FUNCTIONS = frozenset(
    {
        "system",
        "popen",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "posix_spawn",
        "posix_spawnp",
    }
)

# CAN address-family and protocol constants. Exact identifiers only — substrings
# like `CanWriter` or `can_writer` are unrelated and must not trip.
_CAN_CONSTANTS = frozenset({"AF_CAN", "PF_CAN", "CAN_RAW", "CAN_BCM", "CAN_ISOTP", "CAN_EFF_FLAG"})


@dataclass(frozen=True)
class Violation:
    """One static-checker finding.

    Attributes:
        rule: Which ban fired.
        module: Dotted-or-path label of the checked source.
        line: 1-indexed source line.
        message: Human-readable description naming the actual violation.
    """

    rule: str
    module: str
    line: int
    message: str


def check_source(source: str, module: str = "<source>") -> tuple[Violation, ...]:
    """Run all three source bans over one Python source string.

    Args:
        source: Python source to analyse.
        module: Label used in findings.

    Returns:
        (tuple[Violation, ...]) Findings in source order; empty when clean.
    """
    tree = ast.parse(source)
    findings: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            findings.extend(_check_import(node, module))
        elif isinstance(node, ast.ImportFrom):
            findings.extend(_check_import_from(node, module))
        elif isinstance(node, ast.Attribute):
            findings.extend(_check_attribute(node, module))
        elif isinstance(node, ast.Name):
            findings.extend(_check_name(node, module))
    findings.sort(key=lambda finding: finding.line)
    return tuple(findings)


def check_package(root: Path) -> tuple[Violation, ...]:
    """Run the source bans over every `.py` file under a package directory.

    Args:
        root: Package directory to scan.

    Returns:
        (tuple[Violation, ...]) Every violation across the tree, in file then line
        order.
    """
    findings: list[Violation] = []
    for path in sorted(root.rglob("*.py")):
        findings.extend(check_source(path.read_text(encoding="utf-8"), module=str(path)))
    return tuple(findings)


def _check_import(node: ast.Import, module: str) -> list[Violation]:
    """Flag `import` of an in-tree loop or a spawn module."""
    findings: list[Violation] = []
    for alias in node.names:
        findings.extend(_classify_module(alias.name, node.lineno, module))
    return findings


def _check_import_from(node: ast.ImportFrom, module: str) -> list[Violation]:
    """Flag `from x import y` of an in-tree loop, a spawn module, or an os-spawn name."""
    findings: list[Violation] = []
    source_module = node.module or ""
    findings.extend(_classify_module(source_module, node.lineno, module))
    if source_module == "os":
        for alias in node.names:
            if alias.name in _OS_SPAWN_FUNCTIONS:
                findings.append(
                    Violation(
                        rule=RULE_CLI_SPAWN,
                        module=module,
                        line=node.lineno,
                        message=f"imports process-spawning os.{alias.name} (01 FR-SYS-002)",
                    )
                )
    return findings


def _classify_module(name: str, line: int, module: str) -> list[Violation]:
    """Classify a dotted module name against the import bans."""
    findings: list[Violation] = []
    if name == _INTREE_LOOP_PREFIX or name.startswith(f"{_INTREE_LOOP_PREFIX}."):
        findings.append(
            Violation(
                rule=RULE_INTREE_LOOP_IMPORT,
                module=module,
                line=line,
                message=f"imports LeRobot in-tree loop '{name}' (01 FR-SYS-003)",
            )
        )
    root = name.split(".", 1)[0]
    if root in _SPAWN_MODULES:
        findings.append(
            Violation(
                rule=RULE_CLI_SPAWN,
                module=module,
                line=line,
                message=f"imports subprocess-spawning module '{name}' (01 FR-SYS-002)",
            )
        )
    if root == "can":
        findings.append(
            Violation(
                rule=RULE_CAN_SYMBOL,
                module=module,
                line=line,
                message=f"imports CAN stack module '{name}' (09 FR-SIM-098)",
            )
        )
    return findings


def _check_attribute(node: ast.Attribute, module: str) -> list[Violation]:
    """Flag `os.<spawn>`, `pty.spawn`, `subprocess.<x>`, and `<mod>.AF_CAN`."""
    findings: list[Violation] = []
    base = node.value.id if isinstance(node.value, ast.Name) else None
    if base == "os" and node.attr in _OS_SPAWN_FUNCTIONS:
        findings.append(
            Violation(
                rule=RULE_CLI_SPAWN,
                module=module,
                line=node.lineno,
                message=f"calls process-spawning os.{node.attr} (01 FR-SYS-002)",
            )
        )
    if base == "pty" and node.attr == "spawn":
        findings.append(
            Violation(
                rule=RULE_CLI_SPAWN,
                module=module,
                line=node.lineno,
                message="calls pty.spawn (01 FR-SYS-002)",
            )
        )
    if base == "subprocess":
        findings.append(
            Violation(
                rule=RULE_CLI_SPAWN,
                module=module,
                line=node.lineno,
                message=f"references subprocess.{node.attr} (01 FR-SYS-002)",
            )
        )
    if node.attr in _CAN_CONSTANTS:
        findings.append(
            Violation(
                rule=RULE_CAN_SYMBOL,
                module=module,
                line=node.lineno,
                message=f"references CAN constant {node.attr} (09 FR-SIM-098)",
            )
        )
    return findings


def _check_name(node: ast.Name, module: str) -> list[Violation]:
    """Flag a bare CAN constant name brought in by a star or direct import."""
    if node.id in _CAN_CONSTANTS:
        return [
            Violation(
                rule=RULE_CAN_SYMBOL,
                module=module,
                line=node.lineno,
                message=f"references CAN constant {node.id} (09 FR-SIM-098)",
            )
        ]
    return []
