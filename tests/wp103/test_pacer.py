"""The control period is held by a kernel timer, and a missed deadline is a number.

Nothing here asserts that a period was *met*. That is a wall-clock claim, it is false under a
loaded machine by construction, and a test that made it would be the flaky gate `scripts/gates.sh`
splits its lanes to avoid. The accuracy figure belongs to a rig measurement, not to the suite.

What is asserted is the shape that survives any load: a wait answers at least one expiration,
deliberately missing N deadlines counts at least N of them, and the count is what the caller gets
instead of the frames. Overshooting a deadline is monotone under contention — extra load makes
these MORE true — which is the opposite of the accuracy claim.
"""

from __future__ import annotations

import time

import pytest

from backend.actuation.pacer import ON_TIME_EXPIRATIONS, PacerError, TickPacer

# Long enough that a deliberate oversleep of several periods is unambiguous, short enough that the
# whole file costs a few tens of milliseconds.
PERIOD_S = 0.005

# How many periods the oversleep test skips. Above one so the assertion is about counting, not
# about the boundary between on-time and late.
SKIPPED_PERIODS = 3


def test_a_period_of_zero_is_refused() -> None:
    """A zero interval arms a one-shot, so the second wait would block forever."""
    with pytest.raises(ValueError, match="above zero"):
        TickPacer(0.0)


def test_a_negative_period_is_refused() -> None:
    """The same refusal, from the other side of zero."""
    with pytest.raises(ValueError, match="above zero"):
        TickPacer(-PERIOD_S)


def test_a_wait_answers_at_least_one_expiration() -> None:
    """A completed wait means the deadline passed, so the count is never zero."""
    with TickPacer(PERIOD_S) as pacer:
        assert pacer.wait() >= ON_TIME_EXPIRATIONS


def test_missing_deadlines_is_counted_not_replayed() -> None:
    """Sleeping past N deadlines reports them as one number; the periods are not queued as waits.

    This is the property the whole arrangement rests on. Firing the missed periods — sending the
    frames back to back — would put the accumulated setpoint advance on the wire as one step,
    which under MIT is one large torque. The caller is told what it lost instead.
    """
    with TickPacer(PERIOD_S) as pacer:
        pacer.wait()
        time.sleep(PERIOD_S * SKIPPED_PERIODS)
        expirations = pacer.wait()

        assert expirations >= SKIPPED_PERIODS
        assert pacer.overruns >= SKIPPED_PERIODS - ON_TIME_EXPIRATIONS
        assert pacer.waits == 2


def test_an_on_time_wait_adds_no_overrun() -> None:
    """The counter measures missed deadlines, not elapsed waits — a met deadline adds zero."""
    with TickPacer(PERIOD_S) as pacer:
        expirations = pacer.wait()

        assert pacer.overruns == expirations - ON_TIME_EXPIRATIONS


def test_the_elapsed_interval_is_the_expirations_not_the_nominal_period() -> None:
    """A late tick reports the interval that passed, which is what a ramp must advance by."""
    with TickPacer(PERIOD_S) as pacer:
        assert pacer.elapsed_s(1) == pytest.approx(PERIOD_S)
        assert pacer.elapsed_s(SKIPPED_PERIODS) == pytest.approx(PERIOD_S * SKIPPED_PERIODS)


def test_close_is_idempotent() -> None:
    """A `finally` may reach it twice; the second call is not an error."""
    pacer = TickPacer(PERIOD_S)
    pacer.close()
    pacer.close()


def test_waiting_after_close_says_the_pacer_is_closed() -> None:
    """The refusal names the cause rather than surfacing a bare bad-descriptor errno.

    The raise alone is not the property: `os.read(-1, ...)` fails on its own, so a test that only
    asserted `PacerError` would pass with the check deleted. What the check buys is that a caller
    reading the message is told the pacer was closed, instead of being sent to look for a
    descriptor leak.
    """
    pacer = TickPacer(PERIOD_S)
    pacer.close()
    with pytest.raises(PacerError, match="pacer is closed"):
        pacer.wait()


def test_the_context_manager_closes_on_an_exception() -> None:
    """A raise inside the loop releases the timer, like the bus and the lock around it."""
    pacer = TickPacer(PERIOD_S)
    with pytest.raises(RuntimeError), pacer:
        raise RuntimeError("leg failed")
    with pytest.raises(PacerError, match="pacer is closed"):
        pacer.wait()
