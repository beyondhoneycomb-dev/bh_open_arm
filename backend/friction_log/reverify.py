"""Rig re-verification hooks for the hardware-deferred acceptance items (WP-2B-05).

Acceptance ① (no CAN transmit) and ⑥ (no `get_observation`) are decided on this host by
`backend.friction_log.staticcheck`. Five items cannot be — they need a real CAN bus — and
this module is where they are re-run on the rig rather than asserted here. Each hook takes
the rig evidence it needs; called without it, it raises `HardwareDeferredError` so a
deferred check fails loudly instead of reporting a green it never earned. A call on
synthetic data must never be presented as a PASS.

- ② one-writer measurement: exactly one bus sender during the logging session.
- ③ tick-not-interrupted: candump shows zero missed ticks across the logging window.
- ④ real logging frequency/jitter against `f_max_python` and the achieved tick rate.
- ⑤ logging rate not exceeding the tick rate, measured on the bus.
- ⑦ per-cycle frame count matches `PG-CAN-001` (16 keeps the tick condition, 32 breaks it).

The pattern-B OS-level re-check — open the read-only socket and confirm a transmit attempt
is refused by the kernel — is deliberately NOT here: attempting a send needs a transmit
symbol, which the no-transmit scan forbids across this whole tree. That probe lives in the
test harness (`tests/wp2b05`), where a send symbol is not on the logger path.
"""

from __future__ import annotations

from backend.friction_log.constants import BIMANUAL_JOINT_COUNT
from backend.friction_log.errors import HardwareDeferredError, LoggerTransmitError


def reverify_single_writer(bus_senders: tuple[str, ...] | None) -> str:
    """② Confirm exactly one CAN writer held the bus during the session.

    Args:
        bus_senders: Distinct sender identities seen on the bus during logging, from a
            rig capture, or None when no capture is available (deferred).

    Returns:
        (str) The sole writer's identity.

    Raises:
        HardwareDeferredError: If no rig capture was supplied.
        LoggerTransmitError: If more than one sender was seen — the logger became a
            second writer (I-1, FAIL_BLOCKING).
    """
    if bus_senders is None:
        raise HardwareDeferredError("② needs a rig bus capture identifying the senders; deferred")
    writers = tuple(dict.fromkeys(bus_senders))
    if len(writers) != 1:
        raise LoggerTransmitError(f"② expected exactly one CAN writer, saw {writers}")
    return writers[0]


def reverify_ticks_not_interrupted(missed_ticks: int | None) -> None:
    """③ Confirm no scheduler tick was missed across the logging window.

    Args:
        missed_ticks: Missed-tick count from a candump over the whole logging window, or
            None when no capture is available (deferred).

    Raises:
        HardwareDeferredError: If no rig capture was supplied.
        LoggerTransmitError: If any tick was missed — a stopped scheduler path drops the
            arm (RID 9 watchdog → torque loss, I-5, FAIL_BLOCKING).
    """
    if missed_ticks is None:
        raise HardwareDeferredError("③ needs a candump over the logging window; deferred")
    if missed_ticks != 0:
        raise LoggerTransmitError(f"③ scheduler missed {missed_ticks} tick(s) during logging")


def reverify_logging_frequency(
    measured_hz: float | None,
    tick_rate_hz: float | None,
    f_max_python_hz: float | None,
) -> bool:
    """④ Confirm the real logging frequency sits at or below the tick rate and f_max.

    Args:
        measured_hz: Achieved logging frequency on the rig, or None (deferred).
        tick_rate_hz: Achieved scheduler tick rate on the rig, or None (deferred).
        f_max_python_hz: The final `f_max_python`, or None (deferred).

    Returns:
        (bool) True when the logging frequency does not exceed either bound.

    Raises:
        HardwareDeferredError: If any of the three rig figures is missing.
    """
    if measured_hz is None or tick_rate_hz is None or f_max_python_hz is None:
        raise HardwareDeferredError(
            "④ needs the rig logging frequency, tick rate, and final f_max_python; deferred"
        )
    return measured_hz <= tick_rate_hz and measured_hz <= f_max_python_hz


def reverify_logging_not_exceeding_tick(
    logged_frames: int | None,
    bus_ticks: int | None,
) -> None:
    """⑤ Confirm logged frames did not outrun the bus tick count.

    Args:
        logged_frames: Frames the logger captured on the rig, or None (deferred).
        bus_ticks: MIT tick cycles observed on the bus, or None (deferred).

    Raises:
        HardwareDeferredError: If either rig count is missing.
        LoggerTransmitError: If the logger produced more frames than the bus ticked — it
            drove the bus itself (FAIL_BLOCKING).
    """
    if logged_frames is None or bus_ticks is None:
        raise HardwareDeferredError("⑤ needs the rig logged-frame and bus-tick counts; deferred")
    if logged_frames > bus_ticks:
        raise LoggerTransmitError(
            f"⑤ logger produced {logged_frames} frames over {bus_ticks} bus ticks; it drove the bus"
        )


def reverify_frame_count_per_cycle(frames_per_cycle: int | None) -> bool:
    """⑦ Confirm the per-cycle frame count matches `PG-CAN-001` and holds the tick condition.

    Args:
        frames_per_cycle: Frames per cycle measured by `PG-CAN-001`, or None (deferred).

    Returns:
        (bool) True when the pattern-A tick condition holds (exactly
        `BIMANUAL_JOINT_COUNT` frames per cycle); False forces the ≤625 Hz variant.

    Raises:
        HardwareDeferredError: If no `PG-CAN-001` measurement was supplied.
    """
    if frames_per_cycle is None:
        raise HardwareDeferredError("⑦ needs a PG-CAN-001 per-cycle frame count; deferred")
    return frames_per_cycle == BIMANUAL_JOINT_COUNT
