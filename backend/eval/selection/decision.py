"""The selection decision and its recording in WP-4A-05 lineage (`02c` §3.6 CG-4C-06f).

`02c` §3.6 산출: the third product of the WP is that a checkpoint SELECTION decision
is recorded — "누가·무엇을 근거로" (who, on what basis). The human selection itself is
phase-2 (`Human-judgment`, DEFERRED); this is the offline mechanism that makes such a
decision durable and attributable, exercised here on synthetic inputs.

Two properties are load-bearing:

- **A decision is only recordable on determinate evidence.** `from_result` refuses
  to build a decision from an UNDETERMINED `SelectionResult` — recording "I chose X"
  while the interval evidence could not separate X is the forced rank CG-4C-06d
  forbids, one step downstream.
- **Recording goes THROUGH the committed WP-4A-05 lineage store.** The recorder
  links the decision to the selected checkpoint via `register_eval_report`, so the
  decision is discoverable from the checkpoint's lineage (`eval_reports_of`) — that
  is what "선택 결정이 계보에 기록됨" means. It never forks a second lineage; the full
  who/basis text lives in this package's own decision log, keyed by the same
  `CheckpointId` the lineage uses.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

from backend.eval.selection.constants import SELECTION_SELECTED, SELECTION_SOLE_CANDIDATE
from backend.eval.selection.table import SelectionResult

# WP-4A-05 lineage consumption: a decision is keyed by the lineage `CheckpointId` and
# recorded THROUGH the committed lineage store. This import (with `scorecard.py`'s)
# backs the WP-4A-05 -> WP-4C-06 reference edge (`06` §5.6 / CI-16).
from backend.training.lineage import CheckpointId, TrainingLineageStore

_DECISIONS_FILENAME = "selection_decisions.json"
_DETERMINATE_VERDICTS = frozenset({SELECTION_SELECTED, SELECTION_SOLE_CANDIDATE})


class SelectionDecisionError(ValueError):
    """Raised when a selection decision is malformed or built on non-determinate evidence.

    The cases: an empty `decision_id`, `selected_by`, or `basis`; and an attempt to
    build a decision from an UNDETERMINED `SelectionResult` (no selected checkpoint
    exists to record).
    """


@dataclass(frozen=True)
class SelectionDecision:
    """One recorded checkpoint-selection decision (`02c` §3.6 CG-4C-06f).

    Frozen: a decision is a historical fact, attributable to a person and a basis.
    "누가" is `selected_by`; "무엇을 근거로" is `basis`, the evidence summary the
    `SelectionResult` produced (the CI-separation verdict, never an offline metric).

    Attributes:
        decision_id: The decision's unique id, its handle in the lineage store.
        selected_checkpoint: The chosen checkpoint's WP-4A-05 lineage identity.
        task: The task selected for.
        condition: The generic condition value selected under.
        selected_by: Who made the decision (a human selector identity).
        basis: On what basis — the success-rate CI evidence summary.
        lineage_ref: The lineage reference the decision is anchored to.
    """

    decision_id: str
    selected_checkpoint: CheckpointId
    task: str
    condition: str
    selected_by: str
    basis: str
    lineage_ref: str

    @classmethod
    def from_result(
        cls,
        result: SelectionResult,
        decision_id: str,
        selected_by: str,
        lineage_ref: str,
    ) -> SelectionDecision:
        """Build a decision from a determinate selection result.

        Args:
            result: The selection outcome; must have a selected checkpoint (a
                SELECTED or SOLE_CANDIDATE verdict).
            decision_id: The decision's unique id.
            selected_by: Who is recording the decision.
            lineage_ref: The lineage reference to anchor the decision to.

        Returns:
            (SelectionDecision) The assembled decision — not yet recorded.

        Raises:
            SelectionDecisionError: When `result` is UNDETERMINED (or otherwise has
                no selected checkpoint), or a required field is empty.
        """
        if result.verdict not in _DETERMINATE_VERDICTS or result.selected is None:
            raise SelectionDecisionError(
                f"cannot record a decision from a {result.verdict} selection ({result.task}/"
                f"{result.condition}): overlapping CIs give no checkpoint to select (CG-4C-06d)"
            )
        reasons = "; ".join(
            f"{comparison.verdict}:{comparison.reason}" for comparison in result.comparisons
        )
        basis = f"{result.verdict} — {result.reason}" + (f" [{reasons}]" if reasons else "")
        decision = cls(
            decision_id=decision_id,
            selected_checkpoint=result.selected,
            task=result.task,
            condition=result.condition,
            selected_by=selected_by,
            basis=basis,
            lineage_ref=lineage_ref,
        )
        decision.validate()
        return decision

    def validate(self) -> None:
        """Refuse a decision that could not be attributed or traced.

        Raises:
            SelectionDecisionError: On an empty `decision_id`, `selected_by`,
                `basis`, or `lineage_ref`.
        """
        for name, value in (
            ("decision_id", self.decision_id),
            ("selected_by", self.selected_by),
            ("basis", self.basis),
            ("lineage_ref", self.lineage_ref),
        ):
            if not value.strip():
                raise SelectionDecisionError(
                    f"{name} must be non-empty (CG-4C-06f: 누가·무엇을 근거로)"
                )

    def to_dict(self) -> dict[str, object]:
        """Serialise the decision to a JSON-safe map."""
        return {
            "decision_id": self.decision_id,
            "output_dir": self.selected_checkpoint.output_dir,
            "step": self.selected_checkpoint.step,
            "task": self.task,
            "condition": self.condition,
            "selected_by": self.selected_by,
            "basis": self.basis,
            "lineage_ref": self.lineage_ref,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> SelectionDecision:
        """Reconstruct a decision from its serialised form."""
        return cls(
            decision_id=str(raw["decision_id"]),
            selected_checkpoint=CheckpointId(
                output_dir=str(raw["output_dir"]),
                step=int(str(raw["step"])),
            ),
            task=str(raw["task"]),
            condition=str(raw["condition"]),
            selected_by=str(raw["selected_by"]),
            basis=str(raw["basis"]),
            lineage_ref=str(raw["lineage_ref"]),
        )


class SelectionDecisionRecorder:
    """Records selection decisions and links each into WP-4A-05 lineage.

    Ownership/threading: owns a decision-log JSON file guarded by an internal lock
    (matching the sibling lineage stores), and writes the lineage link through the
    `TrainingLineageStore` it is bound to. The lineage store serialises its own
    writes, so a recorder may be shared across threads.
    """

    def __init__(self, base_dir: str | Path, lineage_store: TrainingLineageStore) -> None:
        """Bind the recorder to its decision log and the lineage store.

        Args:
            base_dir: Directory holding this package's decision log.
            lineage_store: The committed WP-4A-05 store the decision is recorded in.
        """
        self.mBaseDir = Path(base_dir)
        self.mBaseDir.mkdir(parents=True, exist_ok=True)
        self.mPath = self.mBaseDir / _DECISIONS_FILENAME
        self.mLineageStore = lineage_store
        self.mLock = threading.Lock()

    def record(self, decision: SelectionDecision) -> None:
        """Persist a decision and record it in the selected checkpoint's lineage.

        The decision text (who/basis) is written to this package's log, and the
        decision is linked to the checkpoint through `register_eval_report`, so the
        selection is discoverable from lineage (`eval_reports_of`). The lineage link
        is written last: a rejected decision leaves the lineage store untouched.

        Args:
            decision: The decision to record; validated before anything is written.

        Raises:
            SelectionDecisionError: When the decision is malformed.
            TrainingLineageError: When the decision id is already linked to a
                different checkpoint in lineage.
        """
        decision.validate()
        with self.mLock:
            log = self._load()
            log[decision.decision_id] = decision.to_dict()
            self._write(log)
            self.mLineageStore.register_eval_report(
                decision.decision_id, decision.selected_checkpoint
            )

    def decisions_of(self, checkpoint: CheckpointId) -> tuple[SelectionDecision, ...]:
        """Return the recorded decisions that selected one checkpoint.

        Args:
            checkpoint: The checkpoint whose selection decisions to read.

        Returns:
            (tuple[SelectionDecision, ...]) The decisions selecting this checkpoint,
                sorted by decision id; empty when none.
        """
        with self.mLock:
            log = self._load()
        decisions = [SelectionDecision.from_dict(raw) for raw in log.values()]
        return tuple(
            sorted(
                (d for d in decisions if d.selected_checkpoint == checkpoint),
                key=lambda d: d.decision_id,
            )
        )

    def lineage_decision_ids(self, checkpoint: CheckpointId) -> tuple[str, ...]:
        """Return the decision ids recorded in lineage for one checkpoint.

        The proof of CG-4C-06f: these ids are read back FROM the committed lineage
        store, not from this package's log — the decision is in the lineage.

        Args:
            checkpoint: The checkpoint to query.

        Returns:
            (tuple[str, ...]) The linked decision ids, sorted.
        """
        return self.mLineageStore.eval_reports_of(checkpoint)

    def _load(self) -> dict[str, dict[str, object]]:
        """Read the decision log, or an empty map when absent."""
        if not self.mPath.is_file():
            return {}
        loaded: dict[str, dict[str, object]] = json.loads(self.mPath.read_text(encoding="utf-8"))
        return loaded

    def _write(self, log: dict[str, dict[str, object]]) -> None:
        """Write the whole decision log back deterministically."""
        self.mPath.write_text(json.dumps(log, indent=2, sort_keys=True), encoding="utf-8")
