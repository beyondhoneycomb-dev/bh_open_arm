"""The immutable lineage slice for degenerate decisions — `FR-TRN-054` (h).

`FR-TRN-054` fixes an eight-element immutable lineage snapshot; element (h) is
"degenerate channel handling decision". The full eight-element record is WP-4A-05's
to assemble (`02c` §1.5), which will consume `DegenerateDecision` as its (h) slot.
This module is the WP-4A-03-owned slice: it persists the decisions immutably and
answers the one query `02c` §1.3 ⑤ (`CG-4A-03e`) requires — "is the three-way
choice queryable in lineage" — without inventing WP-4A-05's schema, exactly as
`backend.training.orchestrator.job_lineage` is WP-4A-01's narrow slice of the same
record.

Persistence and immutability mirror that sibling: a single JSON file so the record
survives the process, a lock because finalisation may be concurrent, and a refusal
to overwrite an existing key so a recorded decision cannot be silently rewritten.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backend.training.degenerate.finding import (
    DegenerateChoice,
    DegenerateDecision,
    DegenerateFinding,
    NormMode,
)
from backend.training.preflight import Component


def _decision_from_row(row: dict[str, Any]) -> DegenerateDecision:
    """Reconstruct a decision from its serialised row.

    Args:
        row: The `asdict`-shaped decision mapping.

    Returns:
        (DegenerateDecision) The reconstructed decision, with its nested finding.
    """
    finding_row = row["finding"]
    component_value = finding_row["component"]
    finding = DegenerateFinding(
        channel_name=str(finding_row["channel_name"]),
        joint=str(finding_row["joint"]),
        component=Component(component_value) if component_value is not None else None,
        norm_mode=NormMode(finding_row["norm_mode"]),
        statistic=float(finding_row["statistic"]),
        threshold=float(finding_row["threshold"]),
        amplification_estimate=float(finding_row["amplification_estimate"]),
    )
    return DegenerateDecision(
        finding=finding,
        choice=DegenerateChoice(row["choice"]),
        rationale=str(row["rationale"]),
    )


class DegenerateLineageStore:
    """A JSON-file store of degenerate decisions, keyed by training-run id.

    Ownership/threading: one instance may be shared across the threads that finalise
    a run; every read-modify-write of the backing file is serialised by an internal
    lock, and a run's decisions are written exactly once — a second write for the
    same run id is refused so the (h) element cannot be mutated after the fact
    (`FR-TRN-054`: the snapshot is immutable).
    """

    def __init__(self, path: Path) -> None:
        """Open (creating the parent if absent) the lineage file at `path`.

        Args:
            path: The JSON file backing the store.
        """
        self.mPath = path
        self.mLock = threading.Lock()
        self.mPath.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        """Read the whole store, or an empty map when the file is absent."""
        if not self.mPath.is_file():
            return {}
        loaded: Any = json.loads(self.mPath.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}

    def record(self, run_id: str, decisions: tuple[DegenerateDecision, ...]) -> None:
        """Write one run's degenerate decisions immutably.

        Args:
            run_id: The training run the decisions belong to.
            decisions: The three-way decisions, one per finding (may be empty for a
                clean dataset — recording the empty set is a positive statement that
                degeneracy was checked and none was found).

        Raises:
            ValueError: When decisions for this run id already exist.
        """
        with self.mLock:
            store = self._load()
            if run_id in store:
                raise ValueError(
                    f"degenerate lineage for {run_id} is already recorded; it is immutable"
                )
            store[run_id] = [asdict(decision) for decision in decisions]
            self.mPath.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")

    def decisions_of(self, run_id: str) -> tuple[DegenerateDecision, ...] | None:
        """Read one run's degenerate decisions back, or None when absent.

        This is the `CG-4A-03e` query: the recorded three-way choice, retrievable
        from lineage.

        Args:
            run_id: The training run.

        Returns:
            (tuple[DegenerateDecision, ...] | None) The decisions, or None when the
                run has no recorded lineage.
        """
        with self.mLock:
            rows = self._load().get(run_id)
        if rows is None:
            return None
        return tuple(_decision_from_row(row) for row in rows)
