"""The hold loop's period is held by the kernel, and a period the work ate is counted.

This loop is why a brakeless arm stays up between engage and release. Past the RID-9 no-send
ceiling the motor stops applying the last MIT command, so an interval that quietly grows is the
arm coming down — and on this rig the whole margin is one tick's work: `rid9_send_period_sec`
0.01 against `rid9_no_send_margin_sec` 0.02.

The precondition that guards the ceiling (`backend.torque_bringup.preconditions`) compares the
*nominal* period against it. It cannot see the work term, so it is satisfied by a loop whose real
interval is anything at all. Sleeping the period after the tick made the real interval
`work + period`; the kernel timer makes it the period, and turns a period the work overran into a
number instead of a silence.

Nothing here asserts a measured duration — that is the wall-clock claim `scripts/gates.sh` splits
its lanes to avoid. What is asserted is the shape: the loop advances on a timer it owns, a stop
ends it, a raising tick stops it and is kept, and the overrun count is carried where the release
can report it.
"""

from __future__ import annotations

import threading
import time

import pytest

from backend.actuation.pacer import TickPacer
from scripts.torque_session import HoldMaintainer

# Short enough that a handful of ticks is a few milliseconds, long enough that the timer is not
# arming inside its own syscall overhead.
FAST_PERIOD_S = 0.002

# How many ticks a test waits for before calling the loop live. Above one so "it ran" is not one
# tick that happened to land before the first wait.
TICKS_BEFORE_LIVE = 3

# How many periods the deliberately slow tick spends, so the pacer must report missed deadlines
# whatever else the machine is doing. Above one because one period late is the boundary case.
OVERRUN_PERIODS = 4

# The bound every wait in this file uses. Generous against `FAST_PERIOD_S`, because a slow shared
# machine must make these tests slow rather than red.
WAIT_BOUND_S = 5.0


class _CountingRig:
    """A rig whose `maintain_hold` counts, and can be told to raise on the Nth tick."""

    def __init__(self, raise_on_tick: int | None = None) -> None:
        self.calls = 0
        self._raise_on_tick = raise_on_tick
        self.reached = threading.Event()

    def maintain_hold(self) -> None:
        """Count one tick, raising instead when this is the scripted one."""
        self.calls += 1
        if self.calls >= TICKS_BEFORE_LIVE:
            self.reached.set()
        if self._raise_on_tick is not None and self.calls == self._raise_on_tick:
            raise RuntimeError("the bus went away mid-hold")


class _SlowRig(_CountingRig):
    """A rig whose tick deliberately spends longer than the period it is driven at."""

    def __init__(self, sleep_s: float) -> None:
        super().__init__()
        self._sleep_s = sleep_s

    def maintain_hold(self) -> None:
        """Count one tick, then hold the loop past its next deadline."""
        super().maintain_hold()
        time.sleep(self._sleep_s)


def _run_until_ticking(rig: _CountingRig, period_s: float = FAST_PERIOD_S) -> HoldMaintainer:
    """Start a maintainer over `rig` and return once it has ticked more than once."""
    maintainer = HoldMaintainer(rig, period_s)
    maintainer.start()
    assert rig.reached.wait(WAIT_BOUND_S), "the maintainer never reached its second tick"
    return maintainer


def test_the_loop_keeps_re_sending_until_it_is_stopped() -> None:
    """The property the arm hangs from: frames keep going out until something says stop."""
    rig = _CountingRig()
    maintainer = _run_until_ticking(rig)

    assert maintainer.stop()
    assert maintainer.ticks >= TICKS_BEFORE_LIVE
    assert maintainer.failure is None


def test_a_tick_that_raises_stops_the_loop_and_is_kept() -> None:
    """A maintenance loop that died silently is an arm nobody is refreshing."""
    rig = _CountingRig(raise_on_tick=TICKS_BEFORE_LIVE)
    maintainer = HoldMaintainer(rig, FAST_PERIOD_S)
    maintainer.start()
    maintainer.join(timeout=WAIT_BOUND_S)

    assert not maintainer.is_alive()
    assert isinstance(maintainer.failure, RuntimeError)


def test_a_tick_that_eats_its_period_is_counted_as_an_overrun() -> None:
    """The count must TRACK the pacer, not merely exist.

    Asserting the field is an int passes against a counter that was never updated — the zero the
    constructor set satisfies it — so the tick here deliberately spends several periods and the
    assertion is that the number moved. Overshooting a deadline is monotone under contention: a
    loaded machine makes this MORE true, which is the opposite direction from a timing assertion
    and is why it belongs in the parallel lane.

    What it pins is the reason the loop was changed at all. A period the work ate is exactly the
    RID-9 lapse that drops a brakeless arm, and before this it left no trace anywhere.
    """
    rig = _SlowRig(sleep_s=FAST_PERIOD_S * OVERRUN_PERIODS)
    maintainer = HoldMaintainer(rig, FAST_PERIOD_S)
    maintainer.start()
    assert rig.reached.wait(WAIT_BOUND_S), "the slow rig never reached its second tick"
    maintainer.stop()

    assert maintainer.overruns > 0


def test_a_period_the_timer_refuses_stops_the_loop_instead_of_free_running() -> None:
    """A zero period arms a one-shot. The loop must die saying so, never spin unpaced.

    This is the sharp direction. A maintainer that fell back to no pacing would re-send as fast
    as the bus accepts, which is not a hold that lapses — it is a hold that floods, and the
    failure would show up as a bus error rather than as the bad period it is.
    """
    rig = _CountingRig()
    maintainer = HoldMaintainer(rig, 0.0)
    maintainer.start()
    maintainer.join(timeout=WAIT_BOUND_S)

    assert not maintainer.is_alive()
    assert isinstance(maintainer.failure, ValueError)
    assert rig.calls == 0


def test_stopping_a_maintainer_that_never_started_is_clean() -> None:
    """The engage records the live session before it engages, so a release meets this case."""
    maintainer = HoldMaintainer(_CountingRig(), FAST_PERIOD_S)

    assert maintainer.stop()


def test_the_loop_paces_on_a_kernel_timer_rather_than_sleeping_the_period() -> None:
    """The mechanism, asserted as a negative: nothing in the loop sleeps.

    `Event.wait(period)` after the work makes the real interval `work + period`, and the RID-9
    precondition checks the nominal period alone — so the regression this pins is invisible to
    the gate that exists to catch it. Reading the source is the only way to see which mechanism
    is in use without asserting on a measured duration.
    """
    import inspect

    source = inspect.getsource(HoldMaintainer.run)

    assert "TickPacer" in source
    assert "_stop_event.wait" not in source


@pytest.mark.parametrize("period_s", [FAST_PERIOD_S, FAST_PERIOD_S * 2])
def test_the_pacer_is_built_at_the_period_the_maintainer_was_given(period_s: float) -> None:
    """The loop's period is the one the manifest set, not a constant the loop chose."""
    with TickPacer(period_s) as pacer:
        assert pacer.period_s == period_s
