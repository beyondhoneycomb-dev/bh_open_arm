"""The control period, held by the kernel instead of by arithmetic.

A loop that paces itself with `sleep(period - work)` does not run at `period`. The real
period is `work + sleep`, and `work` varies by construction — a tick that also builds a
snapshot costs more than the ticks between it, a frame that goes unanswered costs the
reply timeout, and a register read costs a round trip. Correcting the arithmetic does not
fix this, because the term being corrected is the one that moved.

On this rig the error is not cosmetic. `scripts/jog_joint` ramps a joint by advancing a
position setpoint once per frame, and under MIT a position step IS a torque: the motor
answers `kp·(q_des − q)`. A period that stretches while the setpoint advances by its
planned amount asks for the same torque over a longer interval, and one that snaps back
asks for it over a shorter one. That is the visible-jerk failure the sibling Indy7 rig
traced to the same cause, and its fix is this one.

`timerfd` moves the deadline into the kernel. The loop blocks in `read()` until the timer
fires, so lateness accumulated in one tick is not carried into the next — the deadline is
absolute, not measured from when the work happened to finish.

Three properties follow, and each names what enforces it:

1. **An overrun is a number, not a silence** (`wait`). The timer counts its own
   expirations, so a loop that missed two deadlines reads `2` and can say so. A
   `sleep`-paced loop that runs late simply runs late; nothing counts it.
2. **Missed expirations are dropped, never fired** (`wait` returns the count, the caller
   does not replay). Sending the missed frames back to back would put the whole
   accumulated setpoint advance on the wire as one step, which is the exact torque spike
   the pacing exists to prevent. The caller is told how many it lost instead.
3. **The elapsed interval is measured, never nominal** (`wait` returns expirations, and
   `elapsed_s` turns them into seconds). Anything that advances by seconds — a ramp, a
   pacing law, a trajectory clock — must be handed the interval that actually passed, or
   it stretches a move by exactly the amount the loop was late.

`os.timerfd_create` landed in CPython 3.13 and this project is pinned to 3.12
(`pyproject.toml` `requires-python`), so the three syscalls are reached through ctypes.
The struct layout below is `struct itimerspec` on LP64 Linux; there is no other target.

The achieved period is a different measurement from the work time, and both are worth
having: work can sit comfortably under budget while the period walks. `backend.rtbench`
already owns the reporting side (`CycleTimeMeasurement`, overrun share, achieved rate) —
this is the thing that holds the period it reports on.
"""

from __future__ import annotations

import ctypes
import errno
import os
from types import TracebackType

# `struct timespec` and `struct itimerspec` from `<time.h>`, LP64 Linux. Declared rather than
# packed by hand because a wrong offset here is a timer that arms at a plausible-but-wrong
# interval, which reads as jitter rather than as a bug.
_TIME_T = ctypes.c_long


class _Timespec(ctypes.Structure):
    _fields_ = [("tv_sec", _TIME_T), ("tv_nsec", _TIME_T)]


class _Itimerspec(ctypes.Structure):
    _fields_ = [("it_interval", _Timespec), ("it_value", _Timespec)]


# `CLOCK_MONOTONIC` from `<time.h>`. Monotonic and not `CLOCK_REALTIME`: a wall-clock
# adjustment mid-run must not move a control deadline.
CLOCK_MONOTONIC = 1

# The read that blocks until the timer fires returns a `uint64` expiration count.
EXPIRATION_FIELD_BYTES = 8

NANOSECONDS_PER_SECOND = 1_000_000_000

# What one on-time wait returns. Anything above this is that many periods missed.
ON_TIME_EXPIRATIONS = 1

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
_libc.timerfd_create.argtypes = [ctypes.c_int, ctypes.c_int]
_libc.timerfd_create.restype = ctypes.c_int
_libc.timerfd_settime.argtypes = [
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(_Itimerspec),
    ctypes.POINTER(_Itimerspec),
]
_libc.timerfd_settime.restype = ctypes.c_int


class PacerError(OSError):
    """Raised when the kernel refuses to create or arm the timer."""


def _timespec(seconds: float) -> _Timespec:
    """Split a duration in seconds into the whole and nanosecond halves the struct wants.

    Args:
        seconds: The duration.

    Returns:
        (_Timespec) The same duration as `{tv_sec, tv_nsec}`.
    """
    whole = int(seconds)
    return _Timespec(tv_sec=whole, tv_nsec=int(round((seconds - whole) * NANOSECONDS_PER_SECOND)))


class TickPacer:
    """A control period held by a kernel timer, and the count of the deadlines it missed.

    One pacer drives one loop. It is not thread-safe and is not meant to be: the whole
    point of the arrangement it belongs to is that one thread owns the tick, so a second
    thread waiting on the same pacer would be two loops sharing one deadline.

    Attributes:
        period_s: The period the timer was armed at.
        overruns: Deadlines missed since construction, cumulative.
        waits: Completed waits since construction.
    """

    def __init__(self, period_s: float) -> None:
        """Create and arm a periodic timer.

        Args:
            period_s: The control period in seconds; must be above zero.

        Raises:
            ValueError: When the period is not above zero. A zero period arms a timer that
                never fires — `it_interval` of zero means one-shot — so the loop would
                block forever on its second wait rather than run fast.
            PacerError: When the kernel refuses `timerfd_create` or `timerfd_settime`.
        """
        if period_s <= 0.0:
            raise ValueError(f"period must be above zero, got {period_s}")
        self.period_s = period_s
        self.overruns = 0
        self.waits = 0
        fd = _libc.timerfd_create(CLOCK_MONOTONIC, 0)
        if fd < 0:
            code = ctypes.get_errno()
            raise PacerError(code, f"timerfd_create failed: {os.strerror(code)}")
        self._fd = fd
        spec = _Itimerspec(it_interval=_timespec(period_s), it_value=_timespec(period_s))
        if _libc.timerfd_settime(fd, 0, ctypes.byref(spec), None) < 0:
            code = ctypes.get_errno()
            os.close(fd)
            self._fd = -1
            raise PacerError(code, f"timerfd_settime failed: {os.strerror(code)}")

    def wait(self) -> int:
        """Block until the next deadline and report how many passed.

        Returns:
            (int) Expirations since the previous wait. `1` means the deadline was met.
            Above one means the loop was that many periods late, and those periods are
            gone — they are counted here and never replayed as frames.

        Raises:
            PacerError: When the timer has been closed, or the read fails for a reason
                other than an interrupted syscall.
        """
        if self._fd < 0:
            raise PacerError(errno.EBADF, "pacer is closed")
        while True:
            try:
                raw = os.read(self._fd, EXPIRATION_FIELD_BYTES)
            except InterruptedError:
                # A signal delivered mid-wait is not a missed deadline: the timer is still
                # armed and still counting, so the retry blocks until the real one.
                continue
            except OSError as failed:
                raise PacerError(failed.errno or errno.EIO, f"pacer read failed: {failed}") from (
                    failed
                )
            break
        expirations = int.from_bytes(raw, "little")
        self.waits += 1
        self.overruns += expirations - ON_TIME_EXPIRATIONS
        return expirations

    def elapsed_s(self, expirations: int) -> float:
        """Turn a wait's expiration count into the interval that actually passed.

        Args:
            expirations: What `wait` returned.

        Returns:
            (float) Seconds since the previous deadline.
        """
        return expirations * self.period_s

    def close(self) -> None:
        """Disarm and release the timer. Idempotent, so a `finally` may call it twice."""
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> TickPacer:
        """Return the armed pacer."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the timer on every exit path."""
        self.close()
