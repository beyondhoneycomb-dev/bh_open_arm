"""Training job orchestrator (WP-4A-01): queue, GPU-exclusive guard, subprocess runner.

The public surface is the queue service (`TrainingOrchestrator`) and the FR-TRN-027
job contract (`JobSpec`, `JobState`, `DatasetRef`, `JobFilter`). The launcher, GPU
ledger, log store, and lineage store are exported for wiring and testing; nothing
here imports LeRobot in-process — the trainer runs as a subprocess so its OOM
cannot take the CAN-owning backend down (`02c` §1.1).
"""

from __future__ import annotations

from backend.training.orchestrator.checkpoints import Checkpoint, find_last, read_step
from backend.training.orchestrator.gpu_guard import GpuBusyError, GpuLedger
from backend.training.orchestrator.job_lineage import JobLineageRecord, JobLineageStore
from backend.training.orchestrator.launcher import (
    LaunchHandle,
    OutputDirDecision,
    TrainLauncher,
    check_output_dir,
    classify_exit,
)
from backend.training.orchestrator.logstore import LogStore, LogWriter
from backend.training.orchestrator.orchestrator import (
    JobRuntime,
    OrchestratorError,
    TrainingOrchestrator,
)
from backend.training.orchestrator.spec import (
    DatasetRef,
    JobFilter,
    JobSpec,
    JobSpecError,
    JobState,
    apply_filter,
    can_transition,
)

__all__ = [
    "Checkpoint",
    "DatasetRef",
    "GpuBusyError",
    "GpuLedger",
    "JobFilter",
    "JobLineageRecord",
    "JobLineageStore",
    "JobRuntime",
    "JobSpec",
    "JobSpecError",
    "JobState",
    "LaunchHandle",
    "LogStore",
    "LogWriter",
    "OrchestratorError",
    "OutputDirDecision",
    "TrainLauncher",
    "TrainingOrchestrator",
    "apply_filter",
    "can_transition",
    "check_output_dir",
    "classify_exit",
    "find_last",
    "read_step",
]
