"""Acceptance ⑦ — zero CAN dependency, not even vcan.

⑦ requires the whole deliverable to need no CAN device, virtual or real. Two
independent proofs: a static one — no module under ``backend/learning`` imports the
``can`` stack — and a runtime one — importing and exercising every deliverable
loads no ``python-can`` module and needs no ``vcan`` interface. The static scan is
over real imports (parsed from the AST), so prose mentioning "vcan" in a docstring
is not mistaken for a dependency.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

from tests.wp0c07 import LEARNING_DIR

# Any import target whose top-level package is one of these is a CAN dependency.
_CAN_ROOTS = {"can", "python_can", "socketcan"}


def _imported_roots(source: str) -> set[str]:
    """Return the top-level package of every import in a source file."""
    roots: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_module_imports_the_can_stack() -> None:
    """⑦ static: no backend/learning module imports can / python-can / socketcan."""
    modules = sorted(LEARNING_DIR.glob("*.py"))
    assert modules, "expected backend/learning modules to scan"
    for module in modules:
        roots = _imported_roots(module.read_text(encoding="utf-8"))
        offending = roots & _CAN_ROOTS
        assert not offending, f"{module.name} imports CAN stack: {offending}"


def test_exercising_deliverables_loads_no_can_module(tmp_path: Path) -> None:
    """⑦ runtime: building the dataset and running the statistics loads no python-can."""
    # Drop any CAN module a prior test might have imported, then run the full
    # deliverable surface and confirm none reappears.
    for name in [module for module in sys.modules if module.split(".")[0] in _CAN_ROOTS]:
        del sys.modules[name]

    from backend.learning.channel_groups import state_channels
    from backend.learning.normalization_stats import compute_channel_group_stats
    from backend.learning.policy_constraints import (
        DatasetProfile,
        PolicySpec,
        PolicyStructuralValidator,
    )
    from backend.learning.success_rate import SuccessRateAggregator
    from backend.learning.synthetic_dataset import (
        SyntheticDatasetSpec,
        build_synthetic_dataset,
        generate_state_action_arrays,
    )

    spec = SyntheticDatasetSpec()
    build_synthetic_dataset(spec, tmp_path / "ds")
    states, _ = generate_state_action_arrays(spec)
    compute_channel_group_stats(states, state_channels())
    PolicyStructuralValidator().validate(PolicySpec("smolvla"), DatasetProfile(48, 16))
    aggregator = SuccessRateAggregator()
    aggregator.extend([True, False, True])
    aggregator.result()

    can_modules = [module for module in sys.modules if module.split(".")[0] in _CAN_ROOTS]
    assert can_modules == [], f"CAN modules loaded: {can_modules}"


def test_package_import_is_can_free() -> None:
    """Importing the package itself pulls in no CAN module."""
    for name in [module for module in sys.modules if module.split(".")[0] in _CAN_ROOTS]:
        del sys.modules[name]
    importlib.import_module("backend.learning")
    assert not any(module.split(".")[0] in _CAN_ROOTS for module in sys.modules)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
