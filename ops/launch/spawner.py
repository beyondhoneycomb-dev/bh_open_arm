"""Fan-out spawn adapter and its reclaim path.

This is the executor for the fan-out issuing that `05` §0.1 describes: read a manifest's shape,
issue that many instances, and reclaim every one of them on cancellation. Spawning is simulated
— nothing is shelled out to — because the package that owns this adapter is `AI-offline`.

Leak accounting is the point of the reclaim path. An instance that is neither running nor
reclaimed is a leak, and a cancellation that leaves one behind has left work standing on an
invalidated basis without anyone noticing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from ops.cancel.executor import BRANCH_CANCELLED, STEP_COMPLETED, CancelTrace, cancel_stage
from ops.cancel.scheduler import ActuationScheduler, LatchReason
from ops.launch.manifest import Manifest, Stage


class InstanceState(StrEnum):
    """Lifecycle of one spawned workflow instance."""

    RUNNING = "running"
    STEP_COMPLETE = "step_complete"
    CANCELLED = "cancelled"


@dataclass
class FakeWorkflow:
    """A simulated workflow instance.

    Records every lifecycle call it receives into a shared log, so ordering can be observed from
    the callee side rather than trusted from the caller's own trace.
    """

    wp_id: str
    stage_index: int
    ordinal: int
    call_log: list[str] = field(default_factory=list)
    state: InstanceState = InstanceState.RUNNING

    @property
    def instance_id(self) -> str:
        """Identity of this instance.

        Returns:
            (str): Package id, stage index and ordinal, joined.
        """
        return f"{self.wp_id}#s{self.stage_index}#{self.ordinal}"

    def complete_current_step(self) -> None:
        """Run the in-flight step to completion."""
        self.call_log.append(STEP_COMPLETED)
        self.state = InstanceState.STEP_COMPLETE

    def cancel_branch(self) -> None:
        """Cancel this branch and release it."""
        self.call_log.append(BRANCH_CANCELLED)
        self.state = InstanceState.CANCELLED


@dataclass(frozen=True)
class SpawnResult:
    """Outcome of issuing one stage's fan-out."""

    wp_id: str
    stage_index: int
    instances: tuple[FakeWorkflow, ...]


class SpawnAdapter:
    """Issues and reclaims workflow instances for a manifest's stages."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self.clock = clock
        self.instances: list[FakeWorkflow] = []
        self.call_log: list[str] = []

    def spawn(self, manifest: Manifest, stage_index: int) -> SpawnResult:
        """Issue exactly as many instances as the stage's shape calls for.

        Args:
            manifest: Manifest being executed.
            stage_index: Stage to issue.

        Returns:
            (SpawnResult): The issued instances.
        """
        stage = manifest.stage(stage_index)
        issued = tuple(
            FakeWorkflow(
                wp_id=manifest.wp_id,
                stage_index=stage_index,
                ordinal=ordinal,
                call_log=self.call_log,
            )
            for ordinal in range(stage.fanout())
        )
        self.instances.extend(issued)
        return SpawnResult(wp_id=manifest.wp_id, stage_index=stage_index, instances=issued)

    def running(self) -> list[FakeWorkflow]:
        """List instances that have not been cancelled.

        After a reclaim this must be empty; anything remaining is a leaked instance still
        holding resources.

        Returns:
            (list[FakeWorkflow]): Instances still holding resources.
        """
        return [item for item in self.instances if item.state is not InstanceState.CANCELLED]

    def cancel_all(
        self,
        stage: Stage,
        scheduler: ActuationScheduler,
        reason: LatchReason,
        trace: CancelTrace,
    ) -> int:
        """Cancel every live instance under the active stage's policy, and count the reclaim.

        The latch is issued once per instance through `ops.cancel`, never here: this module has
        no latch call of its own, which is what keeps the static check at zero hits.

        Args:
            stage: The stage that is currently active; its policy decides the branch.
            scheduler: Scheduler to latch through on a rig stage.
            reason: Cause recorded with the latch.
            trace: Trace to append observed actions to.

        Returns:
            (int): Number of instances reclaimed.
        """
        reclaimed = 0
        for instance in self.running():
            cancel_stage(
                handle=instance,
                policy=stage.cancel_policy,
                scheduler=scheduler,
                reason=reason,
                now=self.clock(),
                trace=trace,
            )
            reclaimed += 1
        return reclaimed
