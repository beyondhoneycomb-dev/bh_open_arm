"""The Freedrive detection switch: suppress the residual trip, keep the fault trips (WP-2D-04).

`04` FR-MAN-037: during Freedrive the operator's hand force is itself an external-torque
residual, so a normal GMO collision detector trips the instant the arm is guided. This module
switches the residual trip off (or onto a separate, looser threshold set) for Freedrive while
keeping every other detector live — the four the acceptance names: motor ERR nibble,
over-temperature, comm loss, and limit violation. Switching any of those off is the
"detection fully off" FAIL_BLOCKING branch (`DetectionRetainedError`).

Nothing here re-implements a detector. The residual comparison reuses
`backend.gmo.isolate_joints`; the motor-fault and comm-loss trips reuse
`backend.commloss.CommLossWatchdog` (which itself reuses the actuation ERR decoder); the
over-temperature trip reuses `backend.temp_gripper.TemperatureMonitor`. This module adds only
the Freedrive *policy* — which detector is suppressed, which stay — and the limit-violation
check, a geometric comparison against the same soft limits `repulsion` walls off.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from backend.commloss import CommLossWatchdog, WatchdogCause, WatchdogVerdict
from backend.freedrive_walls.errors import DetectionRetainedError, FreedriveConfigError
from backend.gmo import Isolation, isolate_joints
from backend.temp_gripper import MotorThermal, TemperatureMonitor, TemperatureVerdict

# A joint at exactly its soft limit is not yet a violation; only an angle past it by more
# than this tolerance is. It absorbs float round-trip noise on a limit read back through the
# unit crossing, so a joint resting on its declared bound does not trip a spurious violation.
LIMIT_VIOLATION_EPSILON_RAD = 1e-6

# The recv-cycle callable the reused comm-loss watchdog drives, restated here so a caller
# types against this module rather than the watchdog's private alias.
RecvAll = Callable[[], Sequence[int] | None]


class DetectorKind(Enum):
    """The distinct collision/fault detectors a Freedrive tick may run.

    RESIDUAL is the GMO momentum-observer trip — the one Freedrive suppresses. The rest are
    the trips that stay: MOTOR_FAULT (the ERR nibble), COMM_LOSS, TEMPERATURE, LIMIT_VIOLATION,
    and CARTESIAN_WALL (the reused WP-2C-07 keep-out, `cartesian_walls`).
    """

    RESIDUAL = "residual"
    MOTOR_FAULT = "motor_fault"
    COMM_LOSS = "comm_loss"
    TEMPERATURE = "temperature"
    LIMIT_VIOLATION = "limit_violation"
    CARTESIAN_WALL = "cartesian_wall"


# The motor hardware faults `04` FR-MAN-037 names as must-stay: ERR nibble, comm loss, and
# over-temperature. Switching any off during Freedrive turns detection off down to the
# hardware fault, the negative branch's worst case.
HARDWARE_FAULT_DETECTORS = frozenset(
    {DetectorKind.MOTOR_FAULT, DetectorKind.COMM_LOSS, DetectorKind.TEMPERATURE}
)

# Every detector Freedrive must keep live. Limit violation joins the hardware faults
# (FR-MAN-037 keeps limit-violation detection on). The Cartesian keep-out wall is retained by
# reuse (`cartesian_walls`) but is WP-2C-07's own detector, so it is not part of this
# FAIL_BLOCKING guard — its activation is owned there, not switched here.
MANDATORY_RETAINED_DETECTORS = HARDWARE_FAULT_DETECTORS | {DetectorKind.LIMIT_VIOLATION}

# The only detector Freedrive is allowed to suppress: the residual (GMO) trip.
FREEDRIVE_SUPPRESSIBLE_DETECTORS = frozenset({DetectorKind.RESIDUAL})


def assert_freedrive_detection_retained(enabled: Mapping[DetectorKind, bool]) -> None:
    """Refuse a Freedrive detection config that switches off a retained detector.

    `02b` §4.2 WP-2D-04 negative branch: detection fully off — down to the hardware fault —
    is FAIL_BLOCKING. Only the residual may be suppressed; the hardware faults and limit
    violation must stay. A detector absent from `enabled` is treated as on (the safe default).

    Args:
        enabled: Per-detector on/off state.

    Raises:
        DetectionRetainedError: If any mandatory-retained detector is switched off.
    """
    disabled = sorted(
        (kind for kind in MANDATORY_RETAINED_DETECTORS if not enabled.get(kind, True)),
        key=lambda kind: kind.value,
    )
    if disabled:
        raise DetectionRetainedError([kind.value for kind in disabled])


@dataclass(frozen=True)
class FreedriveResidualVerdict:
    """The Freedrive residual policy's outcome for one tick.

    Attributes:
        suppressed: Whether the residual trip is switched off (the default Freedrive state).
        tripped: Whether the residual crossed a threshold — always False when suppressed,
            and only meaningful under a separate threshold set.
        isolation: The reused GMO isolation when a separate threshold set is active, else None.
    """

    suppressed: bool
    tripped: bool
    isolation: Isolation | None


class FreedriveResidualPolicy:
    """Suppresses, or re-thresholds, the residual trip for Freedrive (`04` FR-MAN-037).

    Default: suppressed — a hand-guide force is an external residual, so a normal trip would
    fire on every touch (acceptance ①). A caller may instead supply a separate, looser
    threshold set, and the trip is then evaluated against it through the reused
    `backend.gmo.isolate_joints`.
    """

    def __init__(self, freedrive_thresholds: Sequence[float] | None = None) -> None:
        """Bind the policy to a separate threshold set, or None to suppress the trip.

        Args:
            freedrive_thresholds: Per-joint Freedrive thresholds, Nm; None suppresses the trip.

        Raises:
            FreedriveConfigError: If any threshold is negative.
        """
        if freedrive_thresholds is not None:
            for threshold in freedrive_thresholds:
                if threshold < 0.0:
                    raise FreedriveConfigError(
                        f"Freedrive residual threshold must be non-negative, got {threshold}"
                    )
        self._thresholds = None if freedrive_thresholds is None else tuple(freedrive_thresholds)

    @property
    def suppressed(self) -> bool:
        """Whether the residual trip is fully off (no separate threshold set)."""
        return self._thresholds is None

    def evaluate(self, residual: Sequence[float]) -> FreedriveResidualVerdict:
        """Return the residual verdict for this tick.

        Args:
            residual: The per-joint GMO residual, Nm.

        Returns:
            (FreedriveResidualVerdict) Suppressed (never tripping) or the reused isolation
            against the separate threshold set.
        """
        if self._thresholds is None:
            return FreedriveResidualVerdict(suppressed=True, tripped=False, isolation=None)
        isolation = isolate_joints(residual, self._thresholds)
        return FreedriveResidualVerdict(
            suppressed=False, tripped=isolation.is_contact, isolation=isolation
        )


def limit_violation(
    q: Sequence[float],
    lower_rad: Sequence[float],
    upper_rad: Sequence[float],
    epsilon: float = LIMIT_VIOLATION_EPSILON_RAD,
) -> tuple[int, ...]:
    """Return the joints whose angle is past a soft limit (`04` FR-MAN-037, retained).

    A geometric check, not a residual: it stays live during Freedrive so a joint driven past
    its limit by the hand-guide still trips even while the residual trip is suppressed. The
    bounds are the same soft limits `repulsion` walls off, so the wall and this detector read
    one source.

    Args:
        q: Per-joint angles, radians.
        lower_rad: Per-joint lower soft limits, radians.
        upper_rad: Per-joint upper soft limits, radians.
        epsilon: Tolerance past a bound before it counts as a violation, radians.

    Returns:
        (tuple[int, ...]) The zero-based indices of the violating joints, ascending.

    Raises:
        FreedriveConfigError: If the three vectors are not the same width.
    """
    if not len(q) == len(lower_rad) == len(upper_rad):
        raise FreedriveConfigError(
            f"q, lower and upper must match width, got {len(q)}, {len(lower_rad)}, {len(upper_rad)}"
        )
    return tuple(
        index
        for index, (angle, low, high) in enumerate(zip(q, lower_rad, upper_rad, strict=True))
        if angle < low - epsilon or angle > high + epsilon
    )


@dataclass(frozen=True)
class FreedriveDetectionVerdict:
    """Which detectors tripped on one Freedrive tick.

    Attributes:
        residual: The residual policy's outcome (suppressed or re-thresholded).
        watchdog: The reused comm-loss watchdog's per-cycle verdict (ERR nibble / comm loss).
        temperature: The reused temperature monitor's whole-arm verdict.
        limit_flagged: The joints past a soft limit.
        cartesian_flagged: Whether the reused WP-2C-07 keep-out flagged, or None if not wired.
        tripped_kinds: The detectors that fired — a hold signal for any non-empty set.
    """

    residual: FreedriveResidualVerdict
    watchdog: WatchdogVerdict
    temperature: TemperatureVerdict
    limit_flagged: tuple[int, ...]
    cartesian_flagged: bool | None
    tripped_kinds: tuple[DetectorKind, ...]

    @property
    def tripped(self) -> bool:
        """Whether any detector fired this tick (a Cat-2 hold signal)."""
        return bool(self.tripped_kinds)


class FreedriveDetectionSuite:
    """Runs the retained detectors for a Freedrive tick, with the residual trip switched.

    Ownership: composes the reused detectors (a comm-loss watchdog, a temperature monitor, the
    residual policy) plus the soft-limit bounds and an optional reused Cartesian keep-out
    check. It is structurally impossible to build one without the hardware-fault and
    limit-violation detectors — they are required arguments — so the "detection fully off"
    branch cannot arise through this suite; the boolean-config path is guarded separately by
    `assert_freedrive_detection_retained`.

    Threading: a single caller drives `evaluate` once per tick; the watchdog it holds is
    stateful (latch, silence timer), so one suite serves one arm on one thread.
    """

    def __init__(
        self,
        residual_policy: FreedriveResidualPolicy,
        comm_watchdog: CommLossWatchdog,
        temperature_monitor: TemperatureMonitor,
        lower_rad: Sequence[float],
        upper_rad: Sequence[float],
        cartesian_wall_check: Callable[[], Sequence[object]] | None = None,
    ) -> None:
        """Wire the suite to its reused detectors and the soft-limit bounds.

        Args:
            residual_policy: The Freedrive residual policy (suppress or re-threshold).
            comm_watchdog: The reused motor-fault and comm-loss watchdog.
            temperature_monitor: The reused over-temperature monitor.
            lower_rad: Per-joint lower soft limits, radians.
            upper_rad: Per-joint upper soft limits, radians.
            cartesian_wall_check: Optional reused WP-2C-07 keep-out check returning the
                current violations; None leaves the Cartesian detector unwired.

        Raises:
            FreedriveConfigError: If the two bound vectors are not the same width.
        """
        if len(lower_rad) != len(upper_rad):
            raise FreedriveConfigError(
                f"lower and upper bounds must match width, got {len(lower_rad)}, {len(upper_rad)}"
            )
        self._residual_policy = residual_policy
        self._comm_watchdog = comm_watchdog
        self._temperature_monitor = temperature_monitor
        self._lower_rad = tuple(lower_rad)
        self._upper_rad = tuple(upper_rad)
        self._cartesian_wall_check = cartesian_wall_check

    def evaluate(
        self,
        residual: Sequence[float],
        q: Sequence[float],
        recv_all: RecvAll,
        thermals: Sequence[MotorThermal],
    ) -> FreedriveDetectionVerdict:
        """Run every retained detector for one tick and report which fired.

        The residual runs through the Freedrive policy (suppressed or re-thresholded); the
        motor-fault/comm-loss, temperature, limit-violation and (if wired) Cartesian-wall
        detectors run at full strength, so a hardware fault or a limit breach trips even while
        a hand-guide push is ignored (acceptance ① and ②).

        Args:
            residual: The per-joint GMO residual this tick, Nm.
            q: The per-joint angles this tick, radians.
            recv_all: The bus receive call the comm-loss watchdog drives.
            thermals: The per-motor decoded thermals for the temperature monitor.

        Returns:
            (FreedriveDetectionVerdict) The per-detector outcome and the set that fired.
        """
        residual_verdict = self._residual_policy.evaluate(residual)
        watchdog_verdict = self._comm_watchdog.service(recv_all)
        temperature_verdict = self._temperature_monitor.evaluate(thermals)
        limit_flagged = limit_violation(q, self._lower_rad, self._upper_rad)
        cartesian_flagged = (
            None if self._cartesian_wall_check is None else bool(self._cartesian_wall_check())
        )

        tripped: list[DetectorKind] = []
        if residual_verdict.tripped:
            tripped.append(DetectorKind.RESIDUAL)
        watchdog_kind = _WATCHDOG_CAUSE_TO_KIND.get(watchdog_verdict.cause)
        if watchdog_kind is not None:
            tripped.append(watchdog_kind)
        if temperature_verdict.faulted:
            tripped.append(DetectorKind.TEMPERATURE)
        if limit_flagged:
            tripped.append(DetectorKind.LIMIT_VIOLATION)
        if cartesian_flagged:
            tripped.append(DetectorKind.CARTESIAN_WALL)

        return FreedriveDetectionVerdict(
            residual=residual_verdict,
            watchdog=watchdog_verdict,
            temperature=temperature_verdict,
            limit_flagged=limit_flagged,
            cartesian_flagged=cartesian_flagged,
            tripped_kinds=tuple(tripped),
        )


# An unknown motor status the ERR decoder cannot vouch for is a fault-class hold, grouped
# with the ERR-nibble fault; a silence is the distinct comm-loss trip. A cycle that latched
# nothing carries cause None and maps to no detector.
_WATCHDOG_CAUSE_TO_KIND: dict[WatchdogCause | None, DetectorKind] = {
    WatchdogCause.MOTOR_FAULT: DetectorKind.MOTOR_FAULT,
    WatchdogCause.UNKNOWN_STATUS: DetectorKind.MOTOR_FAULT,
    WatchdogCause.COMM_LOSS: DetectorKind.COMM_LOSS,
}
