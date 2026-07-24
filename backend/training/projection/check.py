"""Static scan proving no `.vel`/`.torque` reaches an action target (`CG-4A-06c`).

`02c` §1.6 ③ requires a static check that finds zero paths where a `.vel`/`.torque`
value enters the action target (`10` FR-TRN-066/074, `11` FR-INF-074, triple
canonical). The rule the scan enforces already exists and is frozen in
`CTR-ACT@v1` (`contracts.action.checker.check_action_target_source`): a torque or
gravity value flowing into a `RequestedPositionAction` / `AcceptedPositionAction`
constructor is the leak. This module reuses that checker — the rule is not
re-implemented — and points it at this package's own source tree so the ablation
infra proves it introduces no such path.

The runtime half of the same guarantee lives in
`selector.select_action_target_indices`, which refuses a poisoned action-name set;
this static half proves the source contains no literal torque-into-target
construction. Together they are the "0 paths" of `CG-4A-06c`. The scan cannot reach
into the LeRobot normalization contract or any code this WP does not own — that
limit is structural (`02c` §1.6), so the scope is exactly this package's files.
"""

from __future__ import annotations

from pathlib import Path

from contracts.action import Violation, check_action_target_source

_PYTHON_SUFFIX = ".py"

# This package's own source tree — the scan's scope. `02c` §1.6 owns
# `backend/training/projection/**`; the WP reads but never edits other trees, so
# the static proof is over exactly the files this WP is accountable for.
PROJECTION_PACKAGE_ROOT = Path(__file__).resolve().parent


def scan_source(source: str, module: str) -> tuple[Violation, ...]:
    """Flag any torque flowing into an action-target constructor in one source.

    Args:
        source: Python source text to analyse.
        module: Dotted module path used in findings.

    Returns:
        (tuple[Violation, ...]) Findings in source order; empty when clean.
    """
    return check_action_target_source(source, module)


def scan_package(root: Path = PROJECTION_PACKAGE_ROOT) -> tuple[Violation, ...]:
    """Scan every Python file under a package root for action-target torque leaks.

    Args:
        root: The package directory to scan; defaults to this package's own tree.

    Returns:
        (tuple[Violation, ...]) Every finding across the tree, in file then source
            order; empty when no file lets a torque into an action target.
    """
    findings: list[Violation] = []
    for path in sorted(root.rglob(f"*{_PYTHON_SUFFIX}")):
        module = ".".join(path.relative_to(root).with_suffix("").parts)
        findings.extend(scan_source(path.read_text(encoding="utf-8"), module))
    return tuple(findings)
