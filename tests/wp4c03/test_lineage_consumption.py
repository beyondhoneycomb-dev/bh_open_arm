"""WP-4A-05 lineage consumption + the WP-4C-04 data-join (no type dependency).

`02c` §3.3 입력: WP-4C-03 consumes the WP-4A-05 lineage and the failure tags. Two
contract facts are proven here:

- A report is keyed by the lineage store's `CheckpointId` — the SAME type
  WP-4A-05 defines — so a success rate cannot exist without a lineage-identified
  checkpoint, and the WP-4A-05 -> WP-4C-03 reference edge is a real static import
  (`06` §5.6 / CI-16), not a phantom.
- Failure tags are counted GENERICALLY, by string value; the stats package never
  imports WP-4C-04's enum or the error-code registry, so the two build in parallel
  with no type dependency (DO-NOT-DUPLICATE).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import backend.eval.stats.aggregator as aggregator_module
import backend.eval.stats.report as report_module
from backend.eval.stats import aggregator as aggregator_pkg
from backend.training.lineage import CheckpointId
from tests.wp4c03.support import checkpoint, episode, report

_STATS_PACKAGE_DIR = Path(inspect.getfile(aggregator_pkg)).parent
_FORBIDDEN_IMPORT_PREFIXES = ("backend.eval.failure", "contracts.errors")


def _imported_modules() -> set[str]:
    """Every module the stats package imports, from an AST scan of its sources."""
    modules: set[str] = set()
    for source_path in _STATS_PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                modules.add(node.module)
    return modules


def test_report_is_keyed_by_lineage_checkpoint_id() -> None:
    """The report's checkpoint is a WP-4A-05 lineage `CheckpointId`."""
    rep = report(n_success=10, n_trials=20)
    assert isinstance(rep.checkpoint, CheckpointId)
    assert rep.checkpoint_hash == "/runs/a@1000"


def test_checkpoint_id_is_the_lineage_type_not_a_fork() -> None:
    """The CheckpointId the stats modules use is WP-4A-05's exact type."""
    assert aggregator_module.CheckpointId is CheckpointId
    assert report_module.CheckpointId is CheckpointId


def test_stats_package_imports_the_lineage_module() -> None:
    """Static: the WP-4A-05 -> WP-4C-03 edge is backed by a real import (CI-16)."""
    imported = _imported_modules()
    assert any(module.startswith("backend.training.lineage") for module in imported), (
        "the stats package must import backend.training.lineage to back the "
        "WP-4A-05 -> WP-4C-03 reference edge"
    )


def test_failure_tags_are_counted_generically_by_value() -> None:
    """Arbitrary tag strings tally by value — no enum membership required."""
    ck = checkpoint()
    from backend.eval.stats import aggregate

    episodes = [
        episode(success=False, seed=0, tags=("POLICY_RUNAWAY", "COLLISION")),
        episode(success=False, seed=1, tags=("COLLISION",)),
        episode(success=False, seed=2, tags=("A_TAG_WP4C03_NEVER_HEARD_OF",)),
        *[episode(success=True, seed=index) for index in range(3, 20)],
    ]
    rep = aggregate("rs-generic", ck, episodes)
    assert rep.failure_tag_counts["COLLISION"] == 2
    assert rep.failure_tag_counts["POLICY_RUNAWAY"] == 1
    assert rep.failure_tag_counts["A_TAG_WP4C03_NEVER_HEARD_OF"] == 1


def test_stats_package_does_not_import_wp4c04_or_error_registry() -> None:
    """Static: the tag join is by value — no import of WP-4C-04's enum or codes."""
    imported = _imported_modules()
    for module in imported:
        for forbidden in _FORBIDDEN_IMPORT_PREFIXES:
            assert not module.startswith(forbidden), (
                f"stats package imports {module!r}; failure tags are a generic data-join, "
                "WP-4C-04 owns the tag/enum definitions (02c §3.3/§3.4)"
            )
