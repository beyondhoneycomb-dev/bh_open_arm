"""CG-4C-06a — no code path sorts or selects a checkpoint by an offline metric.

`FR-INF-062`: `offline_metrics` is a field but never a sort/selection key. The owned
selection tree scans clean, and the scan bites on every ordering context — proving
the check is not vacuous.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.eval import selection
from backend.eval.selection import OfflineMetrics, scan_source, scan_tree
from backend.eval.selection.constants import RULE_NO_OFFLINE_SORT

_SELECTION_ROOT = Path(selection.__file__).parent


def _sort_findings(source: str) -> list[str]:
    """Symbols flagged by the offline-sort/select rule in a source snippet."""
    return [
        v.symbol for v in scan_source(Path("fixture.py"), source) if v.rule == RULE_NO_OFFLINE_SORT
    ]


def test_owned_tree_has_no_offline_sort_or_select() -> None:
    """The selection package contains zero offline-metric ordering paths (CG-4C-06a)."""
    findings = [v for v in scan_tree(_SELECTION_ROOT) if v.rule == RULE_NO_OFFLINE_SORT]
    assert findings == [], f"offline-metric ordering found: {[str(v) for v in findings]}"


def test_scan_bites_on_sort_key() -> None:
    """A `.sort(key=... .val_loss)` is a finding — the scan is not vacuous."""
    assert _sort_findings("cards.sort(key=lambda c: c.offline_metrics.val_loss)\n") == ["val_loss"]


def test_scan_bites_on_max_key() -> None:
    """`max(..., key=... .action_mse)` is a finding."""
    assert _sort_findings("best = max(cards, key=lambda c: c.offline_metrics.action_mse)\n") == [
        "action_mse"
    ]


def test_scan_bites_on_comparison() -> None:
    """Comparing two checkpoints' val_loss directly is a finding."""
    assert _sort_findings("x = a.offline_metrics.val_loss < b.offline_metrics.val_loss\n") == [
        "val_loss"
    ]


def test_scan_bites_on_select_sink() -> None:
    """Passing an offline metric into a selection sink is a finding."""
    assert _sort_findings("select(candidates, by=card.offline_metrics.val_loss)\n") == ["val_loss"]


def test_scan_bites_on_string_key_subscript() -> None:
    """A string-keyed offline metric used as a sort key is a finding."""
    assert _sort_findings('ordered = sorted(cards, key=lambda c: c.metrics["val_loss"])\n') == [
        "val_loss"
    ]


def test_display_use_is_not_flagged() -> None:
    """Formatting an offline metric into a string is legal — display, not ordering."""
    assert _sort_findings('line = f"val_loss = {c.offline_metrics.val_loss:.4f}"\n') == []


def test_sorting_by_success_rate_is_not_flagged() -> None:
    """Sorting by the real success rate is exactly what selection may do."""
    assert _sort_findings("ordered = sorted(cards, key=lambda c: c.report.point_estimate)\n") == []


def test_offline_metrics_type_has_no_ordering() -> None:
    """`OfflineMetrics` is unordered — it cannot even be compared with `<`."""
    left = OfflineMetrics(val_loss=0.1, action_mse=0.02)
    right = OfflineMetrics(val_loss=0.9, action_mse=0.5)
    with pytest.raises(TypeError):
        _ = left < right  # type: ignore[operator]
