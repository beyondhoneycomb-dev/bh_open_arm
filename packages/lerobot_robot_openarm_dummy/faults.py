"""The fault-injection scenario library (acceptance ④, FR-OPS-085).

Six named failures a real device exhibits, each driven through the *real* upstream
that must react to it — no mock stands in for the reaction:

- obs-missing (follower) -> schema/frame validator (0A-02): SCHEMA_REJECTED
- packet-drop (follower) -> drop-counter monitor (FR-SYS-018): DROP_FLAGGED
- stale-source (leader) -> ActuationScheduler (0A-01): SCHEDULER_STALE_HOLD
- bus-off, simulated (scheduler writer) -> scheduler + safety latch: SCHEDULER_LATCH_HOLD
- partial-connect (follower) -> bimanual connect contract: CONNECT_REFUSED
- response-lag (follower) -> observation deadline monitor: DEADLINE_OVERRUN

The stale and bus-off scenarios use `backend.actuation`'s real scheduler on its fake
CAN backend — the sanctioned AI-offline bench, no hardware and no real bus. The
dummy follower carries no CAN, so bus-off is simulated at the scheduler's fake
writer (FR-SIM-098), which is exactly where the follower's bus would be.

A scenario is data plus a named runner; `scenario_library()` returns all six and the
acceptance test asserts each runner produces its declared reaction, and that a
fault-free control produces none — so the reactions are provoked, not perpetual.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from backend.actuation.can_writer import CanBusFaultError
from backend.actuation.emissions import EmissionLabel, ReasonCode
from backend.actuation.harness import FaultInjectionHarness
from contracts.action import DROP_COUNTER_META, RequestedPositionAction
from contracts.units import Deg
from packages.lerobot_robot_openarm_dummy.config import DummyRobotConfig, DummyTeleoperatorConfig
from packages.lerobot_robot_openarm_dummy.injection import (
    OBSERVATION_DEADLINE_SEC,
    FaultKind,
)
from packages.lerobot_robot_openarm_dummy.robot import DummyOpenArmRobot, PartialConnectionError
from packages.lerobot_robot_openarm_dummy.schema import observation_field_diff
from packages.lerobot_robot_openarm_dummy.teleoperator import DummyOpenArmTeleoperator

# A generous number of stalled ticks: freshness is 0.05 s at a 0.001 s bench tick, so
# ~50 ticks age the last target past the window; the loop below is clock-bounded and
# this is only the safety ceiling on iterations.
_MAX_STALL_TICKS = 500


class Reaction(Enum):
    """The upstream reaction a fault scenario is expected to provoke.

    `NONE` is the healthy outcome — a fault-free run of the same pathway — and exists
    so a test can prove each reaction is caused by the fault rather than always
    present.
    """

    NONE = "none"
    SCHEMA_REJECTED = "schema_rejected"
    DROP_FLAGGED = "drop_flagged"
    SCHEDULER_STALE_HOLD = "scheduler_stale_hold"
    SCHEDULER_LATCH_HOLD = "scheduler_latch_hold"
    CONNECT_REFUSED = "connect_refused"
    DEADLINE_OVERRUN = "deadline_overrun"


class DropMonitor:
    """Watches the CAN drop counter across frames (the packet-drop reaction).

    A consumer reading observations flags a drop when the counter advances between
    two frames — the follower reused its last state rather than reporting a new one
    (01 FR-SYS-018).
    """

    def __init__(self) -> None:
        """Start with no observed frame."""
        self._last_count: int | None = None

    def flagged(self, frame: dict[str, object]) -> bool:
        """Report whether the drop counter advanced since the previous frame.

        Args:
            frame: The observation frame just read.

        Returns:
            (bool) True when the counter increased against the last observed frame.
        """
        count = int(frame[DROP_COUNTER_META])
        increased = self._last_count is not None and count > self._last_count
        self._last_count = count
        return increased


class ObservationDeadlineMonitor:
    """Flags an observation that took longer than the cycle budget (response-lag)."""

    def __init__(self, budget_sec: float) -> None:
        """Bind the monitor to a per-observation budget.

        Args:
            budget_sec: The latency ceiling; a slower observation is an overrun.
        """
        self._budget_sec = budget_sec

    def overrun(self, latency_sec: float) -> bool:
        """Report whether an observation latency breaches the budget.

        Args:
            latency_sec: The observed (simulated) observation latency.

        Returns:
            (bool) True when the latency exceeds the budget.
        """
        return latency_sec > self._budget_sec


@dataclass(frozen=True)
class FaultScenario:
    """One fault and the upstream reaction it must provoke.

    Attributes:
        kind: Which fault this is.
        description: What the fault models and which upstream reacts.
        expected: The reaction the runner must observe.
        runner: Drives the fault through the real upstream and returns the reaction.
    """

    kind: FaultKind
    description: str
    expected: Reaction
    runner: Callable[[Path], Reaction]

    def run(self, workdir: Path) -> Reaction:
        """Execute the scenario and return the reaction actually observed.

        Args:
            workdir: A writable directory for device calibration files.

        Returns:
            (Reaction) The reaction the real upstream produced.
        """
        return self.runner(workdir)


def _follower(workdir: Path) -> DummyOpenArmRobot:
    """Build a dummy follower with calibration parked in the work directory."""
    return DummyOpenArmRobot(DummyRobotConfig(id="dummy-follower", calibration_dir=workdir))


def _leader(workdir: Path) -> DummyOpenArmTeleoperator:
    """Build a dummy leader with calibration parked in the work directory."""
    return DummyOpenArmTeleoperator(
        DummyTeleoperatorConfig(id="dummy-leader", calibration_dir=workdir)
    )


def _request_from_action(action: dict[str, float]) -> RequestedPositionAction:
    """Convert a leader's position action into a scheduler position request."""
    return RequestedPositionAction(values=tuple(Deg(float(value)) for value in action.values()))


def _run_obs_missing(workdir: Path) -> Reaction:
    """A follower drops an observation channel; the schema validator rejects it."""
    robot = _follower(workdir)
    robot.fault.drop_channels = ("left_joint_1.pos",)
    robot.connect()
    frame = robot.get_observation()
    missing, _extra = observation_field_diff(frame)
    return Reaction.SCHEMA_REJECTED if missing else Reaction.NONE


def _run_packet_drop(workdir: Path) -> Reaction:
    """A follower reuses its last frame on a dropped packet; the drop monitor flags it."""
    robot = _follower(workdir)
    robot.connect()
    monitor = DropMonitor()

    healthy = robot.get_observation()
    monitor.flagged(healthy)

    robot.fault.packet_drop = True
    dropped = robot.get_observation()
    reused = {key: value for key, value in dropped.items() if key != DROP_COUNTER_META} == {
        key: value for key, value in healthy.items() if key != DROP_COUNTER_META
    }
    return Reaction.DROP_FLAGGED if monitor.flagged(dropped) and reused else Reaction.NONE


def _run_stale_source(workdir: Path) -> Reaction:
    """A leader stalls; the scheduler ages the last target into a stale-source hold."""
    harness = FaultInjectionHarness()
    leader = _leader(workdir)
    leader.connect()

    harness.advance()
    harness.renew()
    published_at = harness.clock.now()
    harness.producer.publish(_request_from_action(leader.get_action()))
    accepted = harness.tick()
    if accepted.label is not EmissionLabel.ACCEPTED_TARGET:
        return Reaction.NONE

    leader.fault.stall = True
    emission = accepted
    ticks = 0
    while (
        harness.clock.now() - published_at <= harness.scheduler.freshness_window_sec
        and ticks < _MAX_STALL_TICKS
    ):
        emission = harness.run_tick(publish=leader.is_producing(), renew=True)
        ticks += 1

    if (
        emission.label is EmissionLabel.STALE_SOURCE_HOLD
        and emission.reason is ReasonCode.MAILBOX_STALE
    ):
        return Reaction.SCHEDULER_STALE_HOLD
    return Reaction.NONE


def _run_bus_off(workdir: Path) -> Reaction:
    """A simulated bus-off faults the writer; the scheduler latches to a safety hold."""
    del workdir
    harness = FaultInjectionHarness()
    harness.run_tick(publish=True, renew=True)

    harness.can_writer.arm_fault()
    harness.advance()
    harness.renew()
    harness.publish()
    bus_fault = False
    try:
        harness.tick()
    except CanBusFaultError:
        bus_fault = True

    harness.latch()
    emission = harness.run_tick(publish=True, renew=True)
    if bus_fault and emission.label is EmissionLabel.SAFETY_LATCH_HOLD:
        return Reaction.SCHEDULER_LATCH_HOLD
    return Reaction.NONE


def _run_partial_connect(workdir: Path) -> Reaction:
    """A follower comes up half-connected; the connect contract refuses to operate."""
    robot = _follower(workdir)
    robot.fault.fail_channels = ("right",)
    try:
        robot.connect()
    except PartialConnectionError:
        return Reaction.CONNECT_REFUSED if not robot.is_connected else Reaction.NONE
    return Reaction.NONE


def _run_response_lag(workdir: Path) -> Reaction:
    """A follower answers past the cycle budget; the deadline monitor flags an overrun."""
    robot = _follower(workdir)
    robot.connect()
    robot.fault.response_lag_sec = OBSERVATION_DEADLINE_SEC * 5
    robot.get_observation()
    monitor = ObservationDeadlineMonitor(OBSERVATION_DEADLINE_SEC)
    return (
        Reaction.DEADLINE_OVERRUN
        if monitor.overrun(robot.last_observation_latency_sec)
        else Reaction.NONE
    )


def scenario_library() -> tuple[FaultScenario, ...]:
    """Return every fault-injection scenario (acceptance ④, at least six).

    Returns:
        (tuple[FaultScenario, ...]) The six named scenarios, each carrying the
        upstream reaction it provokes.
    """
    return (
        FaultScenario(
            kind=FaultKind.OBSERVATION_MISSING,
            description="a sensor fails to report a channel; the frame validator rejects the frame",
            expected=Reaction.SCHEMA_REJECTED,
            runner=_run_obs_missing,
        ),
        FaultScenario(
            kind=FaultKind.PACKET_DROP,
            description="a CAN packet drops; the follower reuses its last frame, drop count bumped",
            expected=Reaction.DROP_FLAGGED,
            runner=_run_packet_drop,
        ),
        FaultScenario(
            kind=FaultKind.STALE_SOURCE,
            description="the leader stalls; the scheduler ages the target into a stale-source hold",
            expected=Reaction.SCHEDULER_STALE_HOLD,
            runner=_run_stale_source,
        ),
        FaultScenario(
            kind=FaultKind.BUS_OFF,
            description="a simulated bus-off faults the writer; the scheduler latches to a hold",
            expected=Reaction.SCHEDULER_LATCH_HOLD,
            runner=_run_bus_off,
        ),
        FaultScenario(
            kind=FaultKind.PARTIAL_CONNECT,
            description="a bimanual arm channel fails to attach; the connect contract refuses",
            expected=Reaction.CONNECT_REFUSED,
            runner=_run_partial_connect,
        ),
        FaultScenario(
            kind=FaultKind.RESPONSE_LAG,
            description="an observation exceeds the cycle budget; the deadline monitor flags it",
            expected=Reaction.DEADLINE_OVERRUN,
            runner=_run_response_lag,
        ),
    )
