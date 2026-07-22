"""The injection abort monitor: four independent causes, each stopping injection at once.

`02b` §2.3 ②: each of the ERR nibble, over-temperature, joint-limit, and human-abort
conditions must immediately stop injection. This module is that detection, and it
reuses rather than reinvents the fault half:

* The ERR nibble and comm-loss causes are the `backend.commloss` watchdog, driven one
  cycle per tick. That watchdog already decodes the Damiao ERR nibble through the frozen
  `OA-MOT` map, handles an unknown nibble fail-closed, and engages the shared one-way
  `SafetyLatch` — so this monitor does not re-decode anything, it consumes the verdict.
* Over-temperature, joint-limit, and human abort are checked here and engage the *same*
  shared latch, so every abort cause ends in one place: a latched Cat-2 hold the
  scheduler emits and only an operator can clear (`12` FR-SAF-043).

Detection only. Like the watchdog, the monitor never writes the bus; stopping injection
is the harness declining to send the next command, and the hold frame is the scheduler's.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from backend.actuation import Clock, SafetyLatch
from backend.commloss import CommLossWatchdog, WatchdogCause
from backend.commloss.watchdog import RecvAll, StatusBytes
from backend.excitation.constants import ABORT_GATE_PREFIX, DEFAULT_MAX_MOTOR_TEMP_C
from backend.excitation.trajectory import JointBounds
from ops.cancel.scheduler import LatchReason


class AbortCause(Enum):
    """Why an injection tick aborted; one member per independent abort condition."""

    MOTOR_FAULT = "motor_fault"
    COMM_LOSS = "comm_loss"
    UNKNOWN_STATUS = "unknown_status"
    OVER_TEMPERATURE = "over_temperature"
    JOINT_LIMIT = "joint_limit"
    HUMAN_ABORT = "human_abort"


# The watchdog's causes map onto the first three abort causes one-to-one; the monitor
# keeps the mapping explicit so a new watchdog cause cannot silently vanish.
_WATCHDOG_CAUSE_TO_ABORT = {
    WatchdogCause.MOTOR_FAULT: AbortCause.MOTOR_FAULT,
    WatchdogCause.COMM_LOSS: AbortCause.COMM_LOSS,
    WatchdogCause.UNKNOWN_STATUS: AbortCause.UNKNOWN_STATUS,
}


@dataclass(frozen=True)
class TickObservation:
    """What the rig reports for one injection tick, the input the monitor judges.

    Attributes:
        status_bytes: This tick's Damiao feedback status bytes (one `data[0]` per motor),
            or None/empty when nothing arrived — the comm-loss case the watchdog times.
        motor_temps_c: Per-joint reported motor temperature, °C.
        positions_rad: Per-joint measured position, radians (v2 convention).
        velocities_rad_s: Per-joint measured velocity, radians/second.
        human_abort: True when the supervising human has pressed abort this tick.
    """

    status_bytes: StatusBytes | None
    motor_temps_c: Sequence[float]
    positions_rad: Sequence[float]
    velocities_rad_s: Sequence[float]
    human_abort: bool


@dataclass(frozen=True)
class AbortDecision:
    """The monitor's verdict for one tick.

    Attributes:
        aborted: Whether this tick aborted injection.
        cause: The distinct cause when aborted, else None.
        index: The trajectory index the tick was for — the resume point on an abort.
        detail: A human-readable locus (implicated joint, temperature, motor code).
    """

    aborted: bool
    cause: AbortCause | None
    index: int
    detail: str


def _single_recv(status_bytes: StatusBytes | None) -> RecvAll:
    """Return a `recv_all` yielding one tick's status bytes to the reused watchdog.

    The watchdog's `service` takes a receive callable; this adapts a single tick's bytes
    to that shape without the monitor holding a bus handle of its own.

    Args:
        status_bytes: This tick's status bytes, or None when nothing arrived.

    Returns:
        (RecvAll) A one-shot receive returning `status_bytes`.
    """

    def _recv() -> StatusBytes | None:
        return status_bytes

    return _recv


class AbortMonitor:
    """Evaluates one tick against all four abort conditions, engaging the shared latch.

    Ownership/threading: holds the arm's shared one-way `SafetyLatch` (also held by the
    reused comm-loss watchdog, so both engage the same hold) and a clock for the latch
    timestamps the temperature/limit/human causes stamp. A single caller drives
    `evaluate` once per tick; the monitor holds no lock and starts no thread.
    """

    def __init__(
        self,
        watchdog: CommLossWatchdog,
        latch: SafetyLatch,
        clock: Clock,
        bounds: Sequence[JointBounds],
        max_temp_c: float = DEFAULT_MAX_MOTOR_TEMP_C,
    ) -> None:
        """Wire the monitor to the reused watchdog and the shared latch.

        Args:
            watchdog: The `backend.commloss` watchdog handling ERR nibble and comm loss;
                it must share `latch` so every cause ends in one hold.
            latch: The arm's shared safety latch, engaged on any abort.
            clock: Time source for the temperature/limit/human latch timestamps.
            bounds: Per-joint position/velocity envelope for the joint-limit check.
            max_temp_c: Over-temperature abort ceiling, °C.
        """
        self._watchdog = watchdog
        self._latch = latch
        self._clock = clock
        self._bounds = tuple(bounds)
        self._max_temp_c = max_temp_c

    def evaluate(self, index: int, observation: TickObservation) -> AbortDecision:
        """Judge one tick, returning the first abort cause found or a clear verdict.

        The order is fault first (the watchdog, covering ERR nibble and comm loss), then
        over-temperature, joint limit, and human abort. Any cause engages the shared latch
        and stops injection; a clear tick returns `aborted=False`.

        Args:
            index: The trajectory index this tick is for.
            observation: The rig's report for this tick.

        Returns:
            (AbortDecision) The verdict, carrying the resume index on an abort.
        """
        fault = self._watchdog.service(_single_recv(observation.status_bytes))
        if fault.latched and fault.cause is not None:
            cause = _WATCHDOG_CAUSE_TO_ABORT[fault.cause]
            code = f" ({fault.motor_code})" if fault.motor_code else ""
            return AbortDecision(True, cause, index, f"watchdog {fault.cause.value}{code}")

        over_temp = self._over_temperature(observation.motor_temps_c)
        if over_temp is not None:
            return self._latch_and_report(AbortCause.OVER_TEMPERATURE, index, over_temp)

        limit = self._joint_limit(observation)
        if limit is not None:
            return self._latch_and_report(AbortCause.JOINT_LIMIT, index, limit)

        if observation.human_abort:
            return self._latch_and_report(AbortCause.HUMAN_ABORT, index, "human pressed abort")

        return AbortDecision(False, None, index, "clear")

    def _over_temperature(self, temps_c: Sequence[float]) -> str | None:
        """Return a locus string for the first over-temperature joint, or None."""
        for joint_index, temperature in enumerate(temps_c):
            if temperature >= self._max_temp_c:
                return f"joint {joint_index} at {temperature:.1f}C >= {self._max_temp_c:.1f}C"
        return None

    def _joint_limit(self, observation: TickObservation) -> str | None:
        """Return a locus string for the first joint outside its bounds, or None."""
        for joint_index, bound in enumerate(self._bounds):
            position = observation.positions_rad[joint_index]
            if position < bound.position_min_rad or position > bound.position_max_rad:
                return f"joint {joint_index} position {position:.4f} rad out of bounds"
            speed = abs(observation.velocities_rad_s[joint_index])
            if speed > bound.velocity_max_rad_s:
                return f"joint {joint_index} speed {speed:.4f} rad/s over bound"
        return None

    def _latch_and_report(self, cause: AbortCause, index: int, detail: str) -> AbortDecision:
        """Engage the shared latch for a monitor-owned cause and report the abort.

        The ERR-nibble and comm-loss causes latch inside the reused watchdog; the three
        causes this monitor owns latch here, with an attributable `EXCITATION_ABORT`
        gate id so an audited hold names which condition stopped the run.
        """
        self._latch.engage(
            LatchReason(
                gate_id=f"{ABORT_GATE_PREFIX}:{cause.value}",
                previous_state="PASS",
                new_state="LATCHED",
                latched_at=self._clock.now(),
            )
        )
        return AbortDecision(True, cause, index, detail)
