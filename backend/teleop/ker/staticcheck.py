"""Static checks the KER package must pass (WP-3B-14 acceptance ①/③/④).

AST-based bans, not grep, so a symbol in a comment or string cannot trip a check and
one used for real cannot hide behind formatting:

- **No CAN symbol (① / FR-TEL-063).** No `import can`, no `AF_CAN`/`PF_CAN`/`CAN_RAW`
  family constant. The KER is USB; a CAN symbol would move it onto the CAN DAG.
- **No inverse kinematics (① / FR-TEL-064).** No import of a kinematics/IK library
  (`openarm_control`, `mink`, any `*.kinematics`) and no call to an IK solver
  (`solve_ik`, `inverse_kinematics`, `integrate_inplace`, `set_target`). An IK call is
  the defect: the KER's joint angles are the command, so IK must be absent, not merely
  unused.
- **No in-tree loop / CLI spawn.** No `lerobot.scripts.*` import and no `subprocess` /
  `os.<spawn>` / `pty.spawn`; the plan owns the teleop loop and never shells out.
- **No re-implemented pipeline machinery (③).** No class or function here names a
  clutch, One-Euro smoother, heartbeat/link-loss state machine, workspace wall, or
  alignment ramp — those belong to WP-3B-09/10 and the KER reuses them, so a
  definition of one here would be a parallel safety path, not the same code path.

Plus one text scan, `scan_forbidden_token`, for the misnamed vendor (④): the device
is an ESP32-S3 module, so the wrong vendor name — supplied by the caller so this
module never spells it — must appear nowhere in the package.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

RULE_CAN_SYMBOL = "can-symbol"
RULE_IK = "inverse-kinematics"
RULE_INTREE_LOOP_IMPORT = "lerobot-intree-loop-import"
RULE_CLI_SPAWN = "cli-subprocess-spawn"
RULE_REIMPLEMENTATION = "pipeline-reimplementation"
RULE_FORBIDDEN_TOKEN = "forbidden-vendor-token"

# The in-tree loop/CLI package. Every teleop/record loop LeRobot ships lives beneath
# it; the ABCs the plugin subclasses (`lerobot.teleoperators`) do not.
_INTREE_LOOP_PREFIX = "lerobot.scripts"

_SPAWN_MODULES = frozenset({"subprocess"})

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

# CAN address-family and protocol constants. Exact identifiers only, so `CanWriter`
# or `can_channels` do not trip.
_CAN_CONSTANTS = frozenset({"AF_CAN", "PF_CAN", "CAN_RAW", "CAN_BCM", "CAN_ISOTP", "CAN_EFF_FLAG"})

# IK/kinematics library roots whose import is an IK dependency, and the solver call
# names that perform or integrate an IK solution (05 §2.6/§2.8).
_IK_MODULE_ROOTS = frozenset({"openarm_control", "mink"})
_IK_CALL_NAMES = frozenset({"solve_ik", "inverse_kinematics", "integrate_inplace", "set_target"})

# Lowercased tokens that name shared-pipeline machinery (WP-3B-09/10). A class or
# function whose name contains one is a re-implementation the KER must not carry.
_REIMPLEMENTATION_TOKENS = frozenset(
    {
        "clutch",
        "oneeuro",
        "one_euro",
        "smoother",
        "heartbeat",
        "linkloss",
        "link_loss",
        "workspace",
        "alignramp",
        "align_ramp",
        "rearm",
    }
)

# The vendor token forbidden by acceptance ④, passed by the caller so this module's own
# source never contains the literal it bans.


@dataclass(frozen=True)
class Violation:
    """One static-checker finding.

    Attributes:
        rule: Which ban fired.
        module: Path or label of the checked source.
        line: 1-indexed source line.
        message: Human-readable description naming the actual violation.
    """

    rule: str
    module: str
    line: int
    message: str


def check_source(source: str, module: str = "<source>") -> tuple[Violation, ...]:
    """Run every AST ban over one Python source string.

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
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            findings.extend(_check_definition(node, module))
    findings.sort(key=lambda finding: finding.line)
    return tuple(findings)


def check_package(root: Path) -> tuple[Violation, ...]:
    """Run every AST ban over each `.py` file under a package directory.

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


def scan_forbidden_token(root: Path, token: str) -> tuple[Violation, ...]:
    """Report each line under a package that contains a forbidden vendor token (④).

    A text scan, not an AST scan: the ban is on the misnaming appearing at all — in a
    string, a comment, or a docstring — because any of those could reach a GUI or a log.

    Args:
        root: Package directory to scan.
        token: The forbidden token, supplied by the caller so this module never spells
            it.

    Returns:
        (tuple[Violation, ...]) One finding per line containing the token.
    """
    findings: list[Violation] = []
    for path in sorted(root.rglob("*.py")):
        for offset, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if token in line:
                findings.append(
                    Violation(
                        rule=RULE_FORBIDDEN_TOKEN,
                        module=str(path),
                        line=offset,
                        message=f"names the vendor {token!r}; the KER is an ESP32-S3 module",
                    )
                )
    return tuple(findings)


def _check_import(node: ast.Import, module: str) -> list[Violation]:
    """Flag `import` of a CAN, IK, in-tree loop, or spawn module."""
    findings: list[Violation] = []
    for alias in node.names:
        findings.extend(_classify_module(alias.name, node.lineno, module))
    return findings


def _check_import_from(node: ast.ImportFrom, module: str) -> list[Violation]:
    """Flag `from x import y` of a banned module or an os-spawn name."""
    findings: list[Violation] = []
    source_module = node.module or ""
    findings.extend(_classify_module(source_module, node.lineno, module))
    if source_module == "os":
        findings.extend(
            Violation(
                rule=RULE_CLI_SPAWN,
                module=module,
                line=node.lineno,
                message=f"imports process-spawning os.{alias.name}",
            )
            for alias in node.names
            if alias.name in _OS_SPAWN_FUNCTIONS
        )
    return findings


def _classify_module(name: str, line: int, module: str) -> list[Violation]:
    """Classify a dotted module name against the import bans."""
    findings: list[Violation] = []
    if name == _INTREE_LOOP_PREFIX or name.startswith(f"{_INTREE_LOOP_PREFIX}."):
        findings.append(
            Violation(RULE_INTREE_LOOP_IMPORT, module, line, f"imports in-tree loop '{name}'")
        )
    root = name.split(".", 1)[0]
    if root in _SPAWN_MODULES:
        findings.append(
            Violation(RULE_CLI_SPAWN, module, line, f"imports subprocess module '{name}'")
        )
    if root == "can":
        findings.append(
            Violation(RULE_CAN_SYMBOL, module, line, f"imports CAN stack module '{name}'")
        )
    if root in _IK_MODULE_ROOTS or name.split(".")[-1] == "kinematics":
        findings.append(
            Violation(RULE_IK, module, line, f"imports inverse-kinematics module '{name}'")
        )
    return findings


def _check_attribute(node: ast.Attribute, module: str) -> list[Violation]:
    """Flag `os.<spawn>`, `pty.spawn`, `subprocess.<x>`, a CAN constant, or an IK call."""
    findings: list[Violation] = []
    base = node.value.id if isinstance(node.value, ast.Name) else None
    if base == "os" and node.attr in _OS_SPAWN_FUNCTIONS:
        findings.append(
            Violation(RULE_CLI_SPAWN, module, node.lineno, f"calls process-spawning os.{node.attr}")
        )
    if base == "pty" and node.attr == "spawn":
        findings.append(Violation(RULE_CLI_SPAWN, module, node.lineno, "calls pty.spawn"))
    if base == "subprocess":
        findings.append(
            Violation(RULE_CLI_SPAWN, module, node.lineno, f"references subprocess.{node.attr}")
        )
    if node.attr in _CAN_CONSTANTS:
        findings.append(
            Violation(RULE_CAN_SYMBOL, module, node.lineno, f"references CAN constant {node.attr}")
        )
    if node.attr in _IK_CALL_NAMES:
        findings.append(Violation(RULE_IK, module, node.lineno, f"calls IK solver {node.attr}"))
    return findings


def _check_name(node: ast.Name, module: str) -> list[Violation]:
    """Flag a bare CAN constant or IK solver name brought in by a direct import."""
    findings: list[Violation] = []
    if node.id in _CAN_CONSTANTS:
        findings.append(
            Violation(RULE_CAN_SYMBOL, module, node.lineno, f"references CAN constant {node.id}")
        )
    if node.id in _IK_CALL_NAMES:
        findings.append(Violation(RULE_IK, module, node.lineno, f"calls IK solver {node.id}"))
    return findings


def _check_definition(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, module: str
) -> list[Violation]:
    """Flag a class/function whose name re-implements shared-pipeline machinery (③)."""
    lowered = node.name.lower()
    hit = next((token for token in _REIMPLEMENTATION_TOKENS if token in lowered), None)
    if hit is None:
        return []
    return [
        Violation(
            rule=RULE_REIMPLEMENTATION,
            module=module,
            line=node.lineno,
            message=(
                f"defines {node.name!r} — pipeline machinery ('{hit}') the KER must reuse "
                "from WP-3B-09/10, not re-implement"
            ),
        )
    ]
