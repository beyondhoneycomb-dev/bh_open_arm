"""GPU admission: the one-line exclusivity guard and its ledger.

Two requirements meet here. FR-TRN-028: at most one training job per GPU unless
the user explicitly permits sharing; a job that cannot get its GPUs stays QUEUED.
FR-TRN-072: never schedule a training job onto a GPU an active real-robot rollout
or teleop session is using, because the rollout's policy forward would contend for
VRAM/SM and jitter the control loop — `02c` §1.1 keeps this a scheduler guard
rather than a design-wide constraint, since control and training hosts separate
naturally.

The guard itself is one predicate (`is_available`). Everything else here is the
ledger it reads: which GPUs are reserved by a job, and which are blocked by a live
session. The ledger holds no lock of its own — the orchestrator serialises every
call to it under the single scheduler lock, which is what makes the QUEUED
decision timing-independent (`02c` §1.1 음성 분기 ①).
"""

from __future__ import annotations

from collections import defaultdict


class GpuBusyError(Exception):
    """Raised when a reservation is attempted on a GPU that is not free."""


class GpuLedger:
    """Tracks which GPUs are reserved by jobs and which are blocked by sessions.

    A GPU maps to the SET of jobs holding it, not a single job, because FR-TRN-028's
    sanctioned exception is co-scheduling: with an explicit share, two jobs may hold
    one GPU. Without a share the set never exceeds one, and the guard enforces that.

    Ownership/threading: not internally synchronised. The orchestrator owns the only
    instance and touches it exclusively while holding its scheduler lock, so
    reservation and the availability check that precedes it are one atomic step.
    """

    def __init__(self, gpu_ids: tuple[int, ...]) -> None:
        """Create a ledger over a fixed pool of GPU ids.

        Args:
            gpu_ids: The physical GPU ids this host schedules over.
        """
        self.mPool = tuple(sorted(set(gpu_ids)))
        self.mHolders: dict[int, set[str]] = defaultdict(set)
        self.mSessionGpus: set[int] = set()

    def is_available(self, gpu_id: int, allow_share: bool) -> bool:
        """The guard: is this GPU schedulable for a training job right now?

        A GPU is available when it is in the pool, not held by a live rollout/teleop
        session, and not reserved by another training job. The explicit share is the
        sanctioned exception to the FR-TRN-028 co-scheduling ban ONLY — it relaxes the
        other-training-job check, never the FR-TRN-072 live-session ban: a GPU driving
        a real robot is never handed a training job, share or no share, because the
        contention it exists to prevent does not care that the user opted in.

        Args:
            gpu_id: The GPU under consideration.
            allow_share: Whether the user explicitly permitted co-scheduling.

        Returns:
            (bool) True when the GPU may take a training job.
        """
        if gpu_id not in self.mPool:
            return False
        if gpu_id in self.mSessionGpus:
            return False
        if allow_share:
            return True
        return not self.mHolders[gpu_id]

    def free_gpus(self, count: int, allow_share: bool) -> tuple[int, ...] | None:
        """Return `count` schedulable GPU ids, or None when too few are free.

        Ids are chosen in pool order so the assignment is deterministic given the
        same ledger state (`02c` §1.1 requires the QUEUED decision be repeatable).

        Args:
            count: How many GPUs the job requested.
            allow_share: Whether the user explicitly permitted co-scheduling.

        Returns:
            (tuple[int, ...] | None) The chosen ids, or None when unavailable.
        """
        chosen = [gpu for gpu in self.mPool if self.is_available(gpu, allow_share)]
        if len(chosen) < count:
            return None
        return tuple(chosen[:count])

    def reserve(self, gpu_ids: tuple[int, ...], job_id: str) -> None:
        """Reserve GPUs for a job.

        The caller has already passed `is_available`/`free_gpus` under the same
        lock, so this only records the holding; a second holder on one GPU is a
        deliberate share, not a conflict. A GPU outside the pool is refused because
        it is not schedulable at all.

        Args:
            gpu_ids: The GPUs to reserve.
            job_id: The job taking them.

        Raises:
            GpuBusyError: When a requested GPU is not in the pool.
        """
        for gpu_id in gpu_ids:
            if gpu_id not in self.mPool:
                raise GpuBusyError(f"GPU {gpu_id} is not in the schedulable pool")
        for gpu_id in gpu_ids:
            self.mHolders[gpu_id].add(job_id)

    def release(self, job_id: str) -> None:
        """Release every GPU a job holds. Idempotent for a job holding none.

        Args:
            job_id: The job whose reservations to drop.
        """
        for holders in self.mHolders.values():
            holders.discard(job_id)

    def set_session_gpus(self, gpu_ids: tuple[int, ...]) -> None:
        """Record which GPUs are held by active rollout/teleop sessions.

        This is the FR-TRN-072 input: while these ids are set, no training job is
        scheduled onto them (barring an explicit share).

        Args:
            gpu_ids: GPUs a live real-robot session currently occupies.
        """
        self.mSessionGpus = {gpu for gpu in gpu_ids if gpu in self.mPool}

    def holders(self, gpu_id: int) -> frozenset[str]:
        """Return the jobs holding a GPU (more than one only under a share).

        Args:
            gpu_id: The GPU to query.

        Returns:
            (frozenset[str]) The holding job ids, empty when the GPU is free.
        """
        return frozenset(self.mHolders[gpu_id])
