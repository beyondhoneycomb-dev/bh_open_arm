"""The replay executor: a pre-verified trajectory, stepped, with a deadman abort (WP-2D-06).

`build_replay` is the ONLY way to a runnable executor, and it interpolates, pre-verifies, and
refuses to return an executor unless the pre-verify passed (`02b` WP-2D-06 ①). There is no
constructor that skips the pre-verify — `ReplayExecutor.__init__` itself rejects a non-ok
result — so the `FAIL_BLOCKING` "pre-verify bypass path" does not exist in this band.

Stepping is per-tick at the trajectory's grid rate; dwell holds and gripper commands are
already baked into the samples by the interpolator, so a tick just advances a cursor. Two
controls sit on top: operator pause/resume/abort, and the deadman. The deadman abort reuses
`backend.deadman.DeadmanMonitor` (③): fed the released signal each tick, it distinguishes a
deadman that has been live and then dropped — a one-way latch to HOLD, the trajectory aborted
and not auto-resumed — from a deadman not yet armed, which simply holds without advancing until
it goes live. A released deadman never advances the cursor either way.

Real motion is out of this band: a `ReplaySample` is what would be routed through the single
`send_action` gateway (I-4) behind the dry-run hard-gate (WP-2A-00), and that real send is
hardware-deferred. This executor produces and sequences the samples; it does not send them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.deadman.monitor import DeadmanMonitor
from backend.replay.interpolate import InterpolatedTrajectory, interpolate_trajectory
from backend.replay.preverify import (
    PreVerifyResult,
    density_step_ceiling_rad,
    run_pre_verify,
    velocity_limits_rad_s,
)
from backend.replay.waypoint import TrajectorySpec


class ReplayState(Enum):
    """The executor's lifecycle state.

    `HOLD` is the one-way terminal for an abort (operator or deadman): the arm stays at the
    commanded sample and the trajectory is not resumed. `PAUSED` is recoverable via `resume`.
    """

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    HOLD = "hold"
    DONE = "done"


class PreVerifyError(Exception):
    """Raised by `build_replay` when the pre-verify fails (`02b` WP-2D-06 ① FAIL_BLOCKING).

    Attributes:
        result: The failing pre-verify verdict, carrying the first violating waypoint index
            and its category.
    """

    def __init__(self, result: PreVerifyResult) -> None:
        """Carry the failing pre-verify result for the caller to report."""
        self.result = result
        super().__init__(
            f"replay refused: pre-verify {result.category.value if result.category else 'failed'} "
            f"at waypoint {result.first_violation_index} — {result.detail}"
        )


@dataclass(frozen=True)
class ReplaySample:
    """One tick's commanded configuration — what would be sent through the gateway (I-4).

    Attributes:
        index: The sample's index in the trajectory.
        t_s: The sample's time on the grid, seconds.
        arm_side: `"right"` or `"left"`.
        q_arm: The moving arm's seven joint angles, radians.
        gripper: The gripper angle, radians.
    """

    index: int
    t_s: float
    arm_side: str
    q_arm: tuple[float, ...]
    gripper: float


class ReplayExecutor:
    """Steps a pre-verified trajectory with operator and deadman controls.

    Not thread-safe: one executor drives one replay, holding the cursor and the latch state.
    Build through `build_replay`, which is the sole entry that runs the pre-verify first.
    """

    def __init__(self, trajectory: InterpolatedTrajectory, pre_verify: PreVerifyResult) -> None:
        """Bind a trajectory to its passing pre-verify; reject a non-ok verdict.

        Args:
            trajectory: The dense, pre-verified trajectory.
            pre_verify: Its pre-verify result; must be `ok` or construction is refused, so no
                path reaches a runnable executor without a passing pre-verify.
        """
        if not pre_verify.ok:
            raise PreVerifyError(pre_verify)
        self._trajectory = trajectory
        self._pre_verify = pre_verify
        self._deadman = DeadmanMonitor()
        self._state = ReplayState.IDLE
        self._cursor = 0

    @property
    def state(self) -> ReplayState:
        """Return the current lifecycle state."""
        return self._state

    @property
    def index(self) -> int:
        """Return the current sample index the executor is commanding."""
        return self._cursor

    @property
    def sample_count(self) -> int:
        """Return the total number of samples in the trajectory."""
        return len(self._trajectory)

    @property
    def done(self) -> bool:
        """Return whether the trajectory has run to its end."""
        return self._state is ReplayState.DONE

    @property
    def held(self) -> bool:
        """Return whether the executor has latched to HOLD (aborted)."""
        return self._state is ReplayState.HOLD

    def residual_ui_note(self) -> str:
        """Return the linear-profile residual-pollution note, or "" (④)."""
        return self._trajectory.residual_ui_note()

    def commanded(self) -> ReplaySample:
        """Return the sample currently commanded (the cursor's position)."""
        return self._sample(self._cursor)

    def start(self) -> ReplaySample:
        """Begin (or restart from IDLE) stepping; command the first sample.

        Returns:
            (ReplaySample) The start pose (sample zero).

        Raises:
            RuntimeError: If called after an abort (HOLD) or completion (DONE); those are
                terminal and require a fresh build.
        """
        if self._state in (ReplayState.HOLD, ReplayState.DONE):
            raise RuntimeError(f"cannot start from terminal state {self._state.value}")
        self._state = ReplayState.RUNNING
        self._cursor = 0
        return self.commanded()

    def pause(self) -> None:
        """Pause a running replay; the arm holds at the current sample (recoverable)."""
        if self._state is ReplayState.RUNNING:
            self._state = ReplayState.PAUSED

    def resume(self) -> None:
        """Resume a paused replay; a HOLD abort is not recoverable this way."""
        if self._state is ReplayState.PAUSED:
            self._state = ReplayState.RUNNING

    def abort(self) -> ReplaySample:
        """Abort immediately and latch to HOLD at the current sample.

        Returns:
            (ReplaySample) The held sample.
        """
        self._state = ReplayState.HOLD
        return self.commanded()

    def tick(self, deadman_released: bool = False) -> ReplaySample:
        """Advance one grid step, honouring the deadman and the lifecycle state (③).

        The deadman is consulted first: a live-then-released edge latches to HOLD (immediate
        abort), and any released state holds the cursor without advancing. Otherwise a RUNNING
        executor advances one sample, reaching DONE past the last; PAUSED, HOLD, and DONE all
        hold the current sample.

        Args:
            deadman_released: Whether the deadman is released (lease expired) as of this tick.

        Returns:
            (ReplaySample) The sample commanded after this tick.
        """
        if self._deadman.observe(deadman_released, latched=self._state is ReplayState.HOLD):
            self._state = ReplayState.HOLD
            return self.commanded()
        if deadman_released:
            return self.commanded()
        if self._state is ReplayState.RUNNING:
            if self._cursor + 1 >= len(self._trajectory):
                self._cursor = len(self._trajectory) - 1
                self._state = ReplayState.DONE
            else:
                self._cursor += 1
        return self.commanded()

    def _sample(self, index: int) -> ReplaySample:
        """Build the `ReplaySample` at a trajectory index.

        Args:
            index: The sample index.

        Returns:
            (ReplaySample) The commanded configuration at that index.
        """
        return ReplaySample(
            index=index,
            t_s=float(self._trajectory.times_s[index]),
            arm_side=self._trajectory.arm_side,
            q_arm=tuple(float(value) for value in self._trajectory.arm[index]),
            gripper=float(self._trajectory.gripper[index]),
        )


def build_replay(
    spec: TrajectorySpec,
    requested_margin_m: float | None = None,
    confirmed_zero_margin: bool = False,
    reference_qpos: list[float] | None = None,
) -> ReplayExecutor:
    """Interpolate, pre-verify, and return a runnable executor — the sole entry (①).

    The pre-verify runs before an executor exists, and a failing pre-verify raises rather than
    returns, so there is no path from a spec to a stepping replay that skips the check.

    Args:
        spec: The multi-point replay sequence.
        requested_margin_m: Collision margin in metres, or None for the `WP-1-06` default.
        confirmed_zero_margin: Whether a zero margin was explicitly confirmed.
        reference_qpos: A collision-free reference configuration, or None for the model neutral.

    Returns:
        (ReplayExecutor) A ready executor for a trajectory that passed all four checks.

    Raises:
        PreVerifyError: If any of the four checks failed; carries the first violation.
    """
    ceiling = density_step_ceiling_rad(requested_margin_m)
    trajectory = interpolate_trajectory(spec, velocity_limits_rad_s(), ceiling)
    result = run_pre_verify(trajectory, requested_margin_m, confirmed_zero_margin, reference_qpos)
    if not result.ok:
        raise PreVerifyError(result)
    return ReplayExecutor(trajectory, result)
