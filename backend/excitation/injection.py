"""The injection harness: preconditions, the drive loop, and resume-by-index (`WP-2B-06`).

This is where the pieces meet under the `02b` §2.3 contract. Before a single command is
sent the harness enforces three hard gates, and the order is deliberate — the cheapest,
most fundamental refusal first:

1. an `FR-MOT-058` torque command path is wired (④ — without it, `τ` cannot be applied,
   so injection cannot start);
2. the `WP-2A-00` dry-run hard-gate has armed (the exciting trajectory requires the
   dry-run to pass);
3. the safe initial state — rest pose, drop-zone isolation, mechanical support — is
   confirmed (① — the first torque on a brakeless arm assumes it is supported).

Then it drives the trajectory one index at a time: sample, observe the rig, evaluate the
abort monitor, and only if clear compose the gravity-hold feed-forward torque
(`WP-2B-02`) and send the command. An abort stops at once and records the trajectory
index, which is exactly the resume point (③); a resume re-checks that the operator has
cleared the latch and re-confirmed the safe state, then continues from that index. A
human who aborts the same session repeatedly surfaces `FAIL_BLOCKING` — the rig, not the
trajectory, is what a repeated stop indicts (`02b` §2.3 negative branch).

The real drive is torque-ON hardware and is deferred: the loop runs here against a
recording torque path and a scripted observer to prove the gates, the abort-on-fault
paths, and resume are real. It never claims a recorded-double run is a real injection.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from backend.dynamics import JOINT2_INDEX, V2_JOINT2_RANGE_RAD
from backend.excitation.abort import AbortCause, AbortMonitor, TickObservation
from backend.excitation.constants import REPEATED_HUMAN_ABORT_LIMIT
from backend.excitation.errors import (
    DryRunGateNotArmedError,
    LatchStillEngagedError,
    TorquePathUnavailableError,
    UnsafeInitialStateError,
)
from backend.excitation.torque_path import TorqueCommand, TorqueCommandPath
from backend.excitation.trajectory import ExcitingTrajectory, JointBounds, TrajectorySample
from backend.gravity import GravityBackend

# The rig's per-tick report source: given the index and the sample about to be commanded,
# return what the arm and the supervising human report. On the real arm this reads motor
# feedback; offline it is a scripted double that injects faults at chosen indices.
Observer = Callable[[int, TrajectorySample], TickObservation]


class InjectionStatus(Enum):
    """How an injection run ended."""

    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass(frozen=True)
class SafeInitialState:
    """The human-confirmed safe initial state injection may begin from (`02b` §2.3 ①).

    Attributes:
        at_rest_pose: The arm is at the agreed rest pose.
        drop_zone_isolated: The area the arm could fall into is cleared and isolated.
        mechanically_supported: The arm is mechanically supported against a torque loss.
        rest_positions_rad: The measured rest pose, radians (v2 convention), which the
            harness cross-checks against the joint bounds and the v2 joint2 range.
    """

    at_rest_pose: bool
    drop_zone_isolated: bool
    mechanically_supported: bool
    rest_positions_rad: Sequence[float]

    @property
    def all_flags_confirmed(self) -> bool:
        """Whether all three human confirmations are present."""
        return self.at_rest_pose and self.drop_zone_isolated and self.mechanically_supported


@dataclass(frozen=True)
class InjectionResult:
    """The outcome of one injection run (a `start` or a `resume`).

    Attributes:
        status: Completed the trajectory, or aborted partway.
        cause: The abort cause when aborted, else None.
        resume_index: Where a subsequent `resume` continues from — the abort index when
            aborted, or `sample_count` when completed (nothing left to resume).
        detail: A human-readable locus from the abort monitor, or a completion note.
        fail_blocking: True when repeated human aborts have escalated this session to a
            rig re-review (`FAIL_BLOCKING`); never set by a fault or limit abort.
    """

    status: InjectionStatus
    cause: AbortCause | None
    resume_index: int
    detail: str
    fail_blocking: bool


class ExcitationInjector:
    """Drives an exciting trajectory through the torque path under the safety gates.

    Ownership/threading: one injector serves one identification session on one arm. It
    holds the dry-run barrier, the torque path, the gravity backend (for the feed-forward
    hold), the abort monitor, the trajectory, and the rig observer, plus the session's
    resume index and human-abort tally. Not thread-safe; a single caller drives it.
    """

    def __init__(
        self,
        barrier_permits_real_send: Callable[[], bool],
        torque_path: TorqueCommandPath | None,
        gravity: GravityBackend,
        monitor: AbortMonitor,
        trajectory: ExcitingTrajectory,
        observer: Observer,
        bounds: Sequence[JointBounds],
        latch_is_active: Callable[[], bool],
    ) -> None:
        """Wire the injector to its collaborators.

        Args:
            barrier_permits_real_send: Reads whether the `WP-2A-00` dry-run barrier is
                armed. Passed as a reader rather than the barrier so this package does not
                re-expose the interlock surface it merely gates on.
            torque_path: The `FR-MOT-058` torque command sink, or None when unwired — the
                ④ precondition refuses the run when it is None.
            gravity: The `WP-2B-02` gravity backend supplying the feed-forward hold torque.
            monitor: The abort monitor evaluated once per tick.
            trajectory: The exciting trajectory to inject.
            observer: The rig's per-tick report source.
            bounds: Per-joint envelope, used to validate the safe-state rest pose.
            latch_is_active: Reads whether the shared safety latch is held, so a resume can
                refuse to continue over an un-acknowledged abort.
        """
        self._permits_real_send = barrier_permits_real_send
        self._torque_path = torque_path
        self._gravity = gravity
        self._monitor = monitor
        self._trajectory = trajectory
        self._observer = observer
        self._bounds = tuple(bounds)
        self._latch_is_active = latch_is_active
        self._resume_index = 0
        self._human_abort_count = 0

    @property
    def resume_index(self) -> int:
        """The trajectory index a `resume` would continue from."""
        return self._resume_index

    @property
    def human_abort_count(self) -> int:
        """How many times a human has aborted this session so far."""
        return self._human_abort_count

    def start(self, safe_state: SafeInitialState) -> InjectionResult:
        """Check the three hard gates and drive the trajectory from index 0.

        Args:
            safe_state: The human-confirmed safe initial state.

        Returns:
            (InjectionResult) The run outcome.

        Raises:
            TorquePathUnavailableError: If no torque command path is wired (④).
            DryRunGateNotArmedError: If the dry-run gate has not armed.
            UnsafeInitialStateError: If the safe initial state is not confirmed (①).
        """
        self._assert_preconditions(safe_state)
        return self._drive(0)

    def resume(self, safe_state: SafeInitialState) -> InjectionResult:
        """Continue from the recorded resume index after an operator-cleared abort.

        Args:
            safe_state: The re-confirmed safe initial state.

        Returns:
            (InjectionResult) The run outcome.

        Raises:
            LatchStillEngagedError: If the abort's safety latch has not been acknowledged.
            TorquePathUnavailableError: If no torque command path is wired (④).
            DryRunGateNotArmedError: If the dry-run gate is no longer armed.
            UnsafeInitialStateError: If the safe initial state is not re-confirmed (①).
        """
        if self._latch_is_active():
            raise LatchStillEngagedError
        self._assert_preconditions(safe_state)
        return self._drive(self._resume_index)

    def _assert_preconditions(self, safe_state: SafeInitialState) -> None:
        """Enforce the three hard gates in order, refusing the run on the first unmet one."""
        if self._torque_path is None:
            raise TorquePathUnavailableError
        if not self._permits_real_send():
            raise DryRunGateNotArmedError
        self._assert_safe_state(safe_state)

    def _assert_safe_state(self, safe_state: SafeInitialState) -> None:
        """Refuse an unconfirmed or out-of-range safe initial state (①)."""
        if not safe_state.all_flags_confirmed:
            raise UnsafeInitialStateError(
                "rest pose, drop-zone isolation, and mechanical support must all be confirmed"
            )
        rest = safe_state.rest_positions_rad
        if len(rest) != len(self._bounds):
            raise UnsafeInitialStateError(
                f"rest pose has {len(rest)} joints, expected {len(self._bounds)}"
            )
        # The v2 joint2 convention is checked before the generic bounds so a v1-frame pose
        # is named as the WP-2B-01 hazard it is, not merely "out of bounds": a joint2 angle
        # in the v1 range identifies against a shifted gravity term and no error would show.
        joint2 = rest[JOINT2_INDEX]
        low, high = V2_JOINT2_RANGE_RAD
        if joint2 < low or joint2 > high:
            raise UnsafeInitialStateError(
                f"rest pose joint2 = {joint2:.4f} rad is outside the v2 range "
                f"[{low}, {high}] — a v1-convention pose would identify against a shifted "
                f"gravity term (WP-2B-01)"
            )
        for joint_index, bound in enumerate(self._bounds):
            position = rest[joint_index]
            if position < bound.position_min_rad or position > bound.position_max_rad:
                raise UnsafeInitialStateError(
                    f"rest pose joint {joint_index} = {position:.4f} rad is outside its bounds"
                )

    def _drive(self, start_index: int) -> InjectionResult:
        """Command the trajectory from `start_index`, stopping on the first abort.

        Args:
            start_index: The trajectory index to begin from.

        Returns:
            (InjectionResult) Completed if the whole remaining trajectory sent, else the
            abort's cause and resume index.
        """
        # Narrow the Optional once, after the precondition proved it non-None, so mypy and
        # the reader both see a concrete path inside the loop.
        torque_path = self._torque_path
        if torque_path is None:
            raise TorquePathUnavailableError

        for index in range(start_index, self._trajectory.sample_count):
            sample = self._trajectory.sample(index)
            observation = self._observer(index, sample)
            decision = self._monitor.evaluate(index, observation)
            if decision.aborted:
                self._resume_index = index
                return self._aborted_result(decision.cause, index, decision.detail)
            torque_path.send(self._command_for(sample))

        self._resume_index = self._trajectory.sample_count
        return InjectionResult(
            status=InjectionStatus.COMPLETED,
            cause=None,
            resume_index=self._trajectory.sample_count,
            detail="trajectory completed",
            fail_blocking=False,
        )

    def _command_for(self, sample: TrajectorySample) -> TorqueCommand:
        """Compose the MIT command for a sample: target state plus the gravity-hold torque."""
        feedforward = self._gravity.tau_grav(sample.positions_rad)
        return TorqueCommand(
            index=sample.index,
            positions_rad=sample.positions_rad,
            velocities_rad_s=sample.velocities_rad_s,
            feedforward_torque_nm=feedforward,
        )

    def _aborted_result(self, cause: AbortCause | None, index: int, detail: str) -> InjectionResult:
        """Build the aborted result, escalating to `FAIL_BLOCKING` on repeated human aborts."""
        fail_blocking = False
        if cause is AbortCause.HUMAN_ABORT:
            self._human_abort_count += 1
            fail_blocking = self._human_abort_count >= REPEATED_HUMAN_ABORT_LIMIT
        return InjectionResult(
            status=InjectionStatus.ABORTED,
            cause=cause,
            resume_index=index,
            detail=detail,
            fail_blocking=fail_blocking,
        )
