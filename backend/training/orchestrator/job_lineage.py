"""Job lineage: the immutable record of where a run stopped.

FR-TRN-032 requires that a cancel preserve the last checkpoint and record the
stopped step "in lineage", and `10` §4.1 lists creating a lineage record among a
job's side effects. This is that record — but only the slice WP-4A-01 owns: the
job-lifecycle facts (which step a run stopped at, which checkpoint survived). It is
deliberately NOT the dataset↔checkpoint reverse index (`backend.dataset.lineage`,
WP-3D-04) and NOT the eight-element FR-TRN-054 snapshot (WP-4A-05); those answer
different questions and carry fields — episode maps, stats hashes — a cancelled
dummy run does not have. Keeping this narrow avoids inventing WP-4A-05's schema
here while still satisfying the acceptance that a stopped step be queryable.

Persistence is a single JSON file so the record survives the process and stays
queryable after the job ends; writes go through a lock because the orchestrator's
monitor threads finalise jobs concurrently.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JobLineageRecord:
    """One run's terminal lineage facts.

    Attributes:
        job_id: The job the record belongs to.
        output_dir: The run output directory.
        stopped_step: The step recorded by the last preserved checkpoint.
        last_checkpoint: Path to that checkpoint directory, or "" when none exists.
        ended: Wall-clock time the run stopped (seconds).
        final_state: The state the run ended in (e.g. "CANCELLED", "DONE").
    """

    job_id: str
    output_dir: str
    stopped_step: int
    last_checkpoint: str
    ended: float
    final_state: str


class JobLineageStore:
    """A JSON-file store of job lineage records, keyed by job id.

    Ownership/threading: one instance is shared across the orchestrator's monitor
    threads; every read-modify-write of the backing file is serialised by an
    internal lock, so concurrent job finalisations cannot lose a record.
    """

    def __init__(self, path: Path) -> None:
        """Open (creating if absent) the lineage file at `path`.

        Args:
            path: The JSON file backing the store.
        """
        self.mPath = path
        self.mLock = threading.Lock()
        self.mPath.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict[str, Any]]:
        """Read the whole store, or an empty map when the file is absent."""
        if not self.mPath.is_file():
            return {}
        loaded: Any = json.loads(self.mPath.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}

    def record(self, entry: JobLineageRecord) -> None:
        """Write one job's lineage record.

        A record is written once per job; a second write for the same job id is
        refused so a run's stopped step cannot be silently overwritten.

        Args:
            entry: The record to store.

        Raises:
            ValueError: When a record for this job id already exists.
        """
        with self.mLock:
            store = self._load()
            if entry.job_id in store:
                raise ValueError(f"lineage for {entry.job_id} is already recorded; it is immutable")
            store[entry.job_id] = asdict(entry)
            self.mPath.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, job_id: str) -> JobLineageRecord | None:
        """Read one job's lineage record back, or None when absent.

        Args:
            job_id: The job.

        Returns:
            (JobLineageRecord | None) The record, or None.
        """
        with self.mLock:
            row = self._load().get(job_id)
        if row is None:
            return None
        return JobLineageRecord(
            job_id=str(row["job_id"]),
            output_dir=str(row["output_dir"]),
            stopped_step=int(row["stopped_step"]),
            last_checkpoint=str(row["last_checkpoint"]),
            ended=float(row["ended"]),
            final_state=str(row["final_state"]),
        )
