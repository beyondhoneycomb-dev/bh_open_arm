"""CG-4C-06c — no checkpoint is auto-deleted on an offline-metric criterion.

`FR-TRN-042`: a checkpoint is never auto-deleted because its loss is low. This
package owns no deletion at all, so the owned tree scans clean; the scan bites when
an offline metric flows into a delete/prune sink, keeping a later edit from quietly
introducing loss-based auto-delete.
"""

from __future__ import annotations

from pathlib import Path

from backend.eval import selection
from backend.eval.selection import ScorecardTable, scan_source, scan_tree
from backend.eval.selection.constants import RULE_NO_LOSS_AUTO_DELETE

_SELECTION_ROOT = Path(selection.__file__).parent


def _delete_findings(source: str) -> list[str]:
    """Symbols flagged by the loss-auto-delete rule in a source snippet."""
    return [
        v.symbol
        for v in scan_source(Path("fixture.py"), source)
        if v.rule == RULE_NO_LOSS_AUTO_DELETE
    ]


def test_owned_tree_has_no_loss_auto_delete() -> None:
    """The selection package contains zero loss-based auto-delete paths (CG-4C-06c)."""
    findings = [v for v in scan_tree(_SELECTION_ROOT) if v.rule == RULE_NO_LOSS_AUTO_DELETE]
    assert findings == [], f"loss-based auto-delete found: {[str(v) for v in findings]}"


def test_scan_bites_on_prune_by_val_loss() -> None:
    """Pruning checkpoints by val_loss is a finding — the scan is not vacuous."""
    assert _delete_findings("prune(checkpoints, threshold=card.offline_metrics.val_loss)\n") == [
        "val_loss"
    ]


def test_scan_bites_on_auto_delete_by_offline_metric() -> None:
    """Feeding an offline metric into an auto-delete sink is a finding."""
    assert _delete_findings("auto_delete(pick_worst(card.offline_metrics.action_mse))\n") == [
        "action_mse"
    ]


def test_deleting_by_success_rate_is_not_a_loss_delete() -> None:
    """A delete keyed on success rate is not a loss-based auto-delete."""
    assert _delete_findings("prune(checkpoints, threshold=card.report.point_estimate)\n") == []


def test_package_exposes_no_deletion_api() -> None:
    """The selection surface offers no delete/prune verb to call."""
    for verb in ("delete", "auto_delete", "prune", "remove", "evict"):
        assert not hasattr(selection, verb)
        assert not hasattr(ScorecardTable, verb)
