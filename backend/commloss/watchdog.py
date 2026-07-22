"""The comm-loss watchdog — silence timer + fault-to-hold wiring (`WP-2A-07`).

`04` FR-MAN-055/056 and `12` FR-SAF-025/027/028/043 split into two detections that
both end in one place, a latched safety hold:

- **Motor fault (ERR nibble).** A Damiao feedback frame carries an ERR nibble in
  its status byte (`data[0]`). This watchdog does *not* re-decode it — the decode
  is the Wave-1 primitive `decode_motor_err` (`backend/actuation/errdecode.py`,
  `WP-1-03` acceptance ⑰), reused by import. The watchdog's own job is the wiring
  the decoder deliberately does not do: on a decoded fault (nibbles `8..E`), engage
  a Cat-2 hold + latch. An unknown nibble the decoder refuses to vouch for is
  handled fail-closed (it latches), never passed through as "healthy".
- **Comm loss (silence).** A fault can only be decoded from a frame that arrived.
  The distinct failure is *no frame at all*: if `recv_all()` returns nothing for
  `comm_timeout_sec` (default 10 ms), the bus is silent and the arm must stop.
  This is the RID-9 `TIMEOUT` case (`12` FR-SAF-027) — a timer, not a decode.

Ownership and boundaries:

- **Detection only; never writes the bus.** Like the collision guard (`WP-1-03`
  `guard.py`), the watchdog engages a shared `SafetyLatch` and returns. The hold
  frame is emitted by the scheduler tick, not here — cutting the command stream
  would drop a brakeless arm (I-1/I-3, `12` FR-SAF-073). The Cat-2 hold *is* the
  latch: once engaged the scheduler emits `SAFETY_LATCH_HOLD` every tick.
- **The latch is one-way (`FR-SAF-043`).** A receive cycle can only ever engage
  the latch, never clear it. A healthy frame arriving after a fault must not resume
  motion — that would be the auto-resume the negative branch forbids. `service`
  reports the held state instead of re-evaluating, which is that guarantee.
- **Clear is an operator act (`FR-SAF-028`).** The only exit is `clear_error`, and
  only with an explicit `OperatorConfirmation`; it acknowledges the latch and hands
  back the Clear-Error CAN payload for the bus owner to emit.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from backend.actuation import (
    Clock,
    SafetyLatch,
    UnknownErrNibbleError,
    decode_motor_err,
)
from backend.commloss.constants import (
    CLEAR_ERROR_PAYLOAD,
    DEFAULT_COMM_TIMEOUT_SEC,
    WATCHDOG_GATE_PREFIX,
)
from ops.cancel.scheduler import LatchReason

# A `recv_all()` yields one status byte (`data[0]`) per motor feedback frame it
# drained this cycle. The upstream frame's remaining bytes are position/velocity/
# torque, owned elsewhere; the watchdog consumes only the ERR-bearing status byte.
StatusBytes = Sequence[int]
RecvAll = Callable[[], StatusBytes | None]


class WatchdogCause(Enum):
    """Why the watchdog latched — a distinct cause per detection (for the audit)."""

    MOTOR_FAULT = "motor_fault"
    COMM_LOSS = "comm_loss"
    UNKNOWN_STATUS = "unknown_status"


@dataclass(frozen=True)
class WatchdogVerdict:
    """The watchdog's outcome for one receive cycle.

    Attributes:
        latched: Whether the arm is in a latched hold after this cycle.
        newly_latched: Whether this cycle is the one that engaged the latch —
            distinguishing the detecting cycle from every held cycle after it.
        cause: The distinct cause when this cycle latched, else None.
        motor_code: The `OA-MOT` code for a decoded motor fault, else None.
    """

    latched: bool
    newly_latched: bool
    cause: WatchdogCause | None
    motor_code: str | None


_CLEAR = WatchdogVerdict(latched=False, newly_latched=False, cause=None, motor_code=None)
_HELD = WatchdogVerdict(latched=True, newly_latched=False, cause=None, motor_code=None)


@dataclass(frozen=True)
class OperatorConfirmation:
    """An operator's explicit confirmation that a latched fault may be cleared.

    Constructing one — which requires naming the operator — is the deliberate act
    `12` FR-SAF-028 requires. A `clear_error` call given None instead is refused,
    so "just clear it" has no code path; the confirmation cannot be defaulted in.

    Attributes:
        operator: Identifier of the operator confirming the clear.
    """

    operator: str


@dataclass(frozen=True)
class ClearErrorCommand:
    """The Damiao Clear-Error CAN command a confirmed clear produces.

    The watchdog returns this rather than sending it: the scheduler is the single
    CAN writer (I-1), so the bus owner emits the payload. Its existence here is the
    `FR-SAF-028` command, gated behind operator confirmation.

    Attributes:
        payload: The 8-byte Clear-Error CAN payload.
    """

    payload: bytes


class UnconfirmedClearError(RuntimeError):
    """Raised when `clear_error` is called without an explicit operator confirmation.

    A latch cleared without a confirmed operator act would be the auto-resume
    `12` FR-SAF-043 forbids, so the missing confirmation is a hard error, not a
    silent no-op the caller might read as success.
    """

    def __init__(self) -> None:
        """Build the error naming the missing confirmation."""
        super().__init__(
            "clear_error requires an explicit OperatorConfirmation: a latched motor "
            "fault is released only by an acknowledged operator act, never "
            "automatically (12 FR-SAF-028, FR-SAF-043)"
        )


class CommLossWatchdog:
    """A detection-only watchdog that sets — but never itself clears — a safety latch.

    Ownership: holds the arm's shared one-way `SafetyLatch` (a Wave-1 primitive, set
    by any detection source and cleared only by an operator ack), a clock for latch
    timestamps and silence measurement, and the last time a frame was seen. It holds
    no CAN handle and no writer, which is the structural half of "never writes the
    bus": engaging the latch is the whole of what it does when it decides to stop.

    Threading: a single caller drives `service` once per receive cycle from the
    control loop; the watchdog holds no lock and starts no thread of its own.
    """

    def __init__(
        self,
        latch: SafetyLatch,
        clock: Clock,
        comm_timeout_sec: float = DEFAULT_COMM_TIMEOUT_SEC,
    ) -> None:
        """Wire the watchdog to the shared latch and clock.

        Args:
            latch: The arm's shared safety latch; engaged on any detection and
                cleared only by an operator-confirmed `clear_error`.
            clock: Monotonic time source for latch timestamps and the silence
                interval. The fault-injection harness passes a `ManualClock`.
            comm_timeout_sec: Silence ceiling before a comm loss latches. A frame
                gap of at least this many seconds is a safe-stop condition.
        """
        self._latch = latch
        self._clock = clock
        self._comm_timeout_sec = comm_timeout_sec
        # Assume the link is alive at construction: the arm arms healthy, so the
        # silence interval is measured from now, not from an implicit zero that
        # would read as instantly-timed-out on the first cycle.
        self._last_seen = clock.now()

    @property
    def is_latched(self) -> bool:
        """Whether the arm is in a latched safety hold (until an operator ack clears it)."""
        return self._latch.is_active

    def service(self, recv_all: RecvAll) -> WatchdogVerdict:
        """Run one receive cycle: decode any frames, then check for silence.

        Order matters. A latched arm short-circuits first: once held, a cycle may
        not clear the latch nor report a resume, however healthy the bus now looks
        (`FR-SAF-043`). Otherwise the frames `recv_all` drained are decoded — any
        fault latches immediately — and only if none arrived is the silence timer
        checked against `comm_timeout_sec`.

        Args:
            recv_all: The bus receive call, returning this cycle's status bytes
                (one `data[0]` per motor frame) or an empty sequence / None when
                nothing arrived. The mocked-timeout case returns empty.

        Returns:
            (WatchdogVerdict) The hold state after this cycle and, when this cycle
            latched, the distinct cause.
        """
        if self._latch.is_active:
            return _HELD

        frames = recv_all() or ()
        now = self._clock.now()
        if frames:
            self._last_seen = now
            for status_byte in frames:
                verdict = self._inspect(status_byte, now)
                if verdict.latched:
                    return verdict
            return _CLEAR

        if now - self._last_seen >= self._comm_timeout_sec:
            return self._latch_for(WatchdogCause.COMM_LOSS, None, now)
        return _CLEAR

    def clear_error(self, confirmation: OperatorConfirmation | None) -> ClearErrorCommand:
        """Clear a latched fault — only on an explicit operator confirmation.

        `12` FR-SAF-028: the fault is cleared by the Damiao Clear-Error CAN command,
        and only after the operator explicitly confirms. `12` FR-SAF-043: the latch
        is released by this acknowledged act alone, never automatically. The command
        payload is returned for the bus owner to emit; the watchdog does not send it.

        Args:
            confirmation: The operator's explicit confirmation. None is refused.

        Returns:
            (ClearErrorCommand) The Clear-Error CAN payload to emit.

        Raises:
            UnconfirmedClearError: When called without a confirmation — the
                latch stays engaged, because an unconfirmed clear is the auto-resume
                the latch exists to prevent.
        """
        if confirmation is None:
            raise UnconfirmedClearError
        self._latch.acknowledge()
        return ClearErrorCommand(payload=CLEAR_ERROR_PAYLOAD)

    def _inspect(self, status_byte: int, now: float) -> WatchdogVerdict:
        """Decode one status byte through the reused decoder, latching on a fault.

        A nibble the decoder cannot vouch for (`UnknownErrNibbleError`) latches
        fail-closed rather than propagating: an unrecognised status is not healthy,
        and letting the exception escape would tear down the receive loop that keeps
        the arm held.
        """
        try:
            decoded = decode_motor_err(status_byte)
        except UnknownErrNibbleError:
            return self._latch_for(WatchdogCause.UNKNOWN_STATUS, None, now)
        if decoded.is_fault:
            return self._latch_for(WatchdogCause.MOTOR_FAULT, decoded.code, now)
        return _CLEAR

    def _latch_for(
        self,
        cause: WatchdogCause,
        motor_code: str | None,
        now: float,
    ) -> WatchdogVerdict:
        """Engage the shared latch with an attributable reason and report the detection."""
        gate_id = f"{WATCHDOG_GATE_PREFIX}:{cause.value}"
        if motor_code is not None:
            gate_id = f"{gate_id}:{motor_code}"
        self._latch.engage(
            LatchReason(
                gate_id=gate_id,
                previous_state="PASS",
                new_state="LATCHED",
                latched_at=now,
            )
        )
        return WatchdogVerdict(latched=True, newly_latched=True, cause=cause, motor_code=motor_code)
