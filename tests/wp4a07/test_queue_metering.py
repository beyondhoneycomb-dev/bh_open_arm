"""CG-4A-07f — the queue-exhaustion counter rises in proportion to an injected dummy delay.

`FR-INF-012` requires the exhaustion count and ratio to be *live*, not decorative. The
delay is injected on the committed dummy robot (`FaultInjection.response_lag_sec`), which
lengthens each chunk's inference latency, so a larger delay starves the action queue more
often. The test drives increasing delays and asserts the exhaustion count increases
monotonically and materially — proof the metering is alive — and that a fast policy
barely starves. The `FR-INF-020` residual series and the reset are checked too.
"""

from __future__ import annotations

from backend.actuation import ManualClock, TargetMailbox
from backend.inference.adapter import InferenceBackend, InferenceSession, RtcParams
from packages.lerobot_robot_openarm_dummy import FaultInjection
from tests.wp4a07.support import FixturePolicy, make_dummy_robot

_FPS = 30.0
_TICKS = 300


def _run_rtc_with_delay(delay_multiple: float) -> InferenceSession:
    """Run `_TICKS` RTC ticks with an injected observation lag of `delay_multiple * dt`.

    Args:
        delay_multiple: The injected lag as a multiple of the control period.

    Returns:
        (InferenceSession) The session after the run, for its meter.
    """
    robot = make_dummy_robot()
    robot.fault = FaultInjection(response_lag_sec=delay_multiple / _FPS)
    session = InferenceSession(
        robot=robot,
        mailbox=TargetMailbox(),
        clock=ManualClock(),
        policy=FixturePolicy(),
        fps=_FPS,
    )
    session.switch_backend(InferenceBackend.RTC, RtcParams())
    for _ in range(_TICKS):
        session.rtc_tick()
    return session


def test_exhaustion_rises_with_injected_delay() -> None:
    """Exhaustion count is monotonic non-decreasing in the injected delay, and materially so.

    The fixture chunk length is 8, so latencies above 8*dt starve the queue; the delays
    span that threshold, so exhaustion climbs from near-zero to a large fraction.
    """
    delays = [0.0, 8.0, 16.0, 32.0]
    counts = [_run_rtc_with_delay(delay).meter.exhaustion_ticks for delay in delays]

    assert counts == sorted(counts)
    assert counts[0] <= 5
    assert counts[-1] > counts[0]
    assert _run_rtc_with_delay(32.0).meter.exhaustion_ratio > 0.5


def test_ratio_tracks_count_over_total() -> None:
    """The exhaustion ratio is exactly count / total, over exactly `_TICKS` metered ticks."""
    session = _run_rtc_with_delay(16.0)
    meter = session.meter
    assert meter.total_ticks == _TICKS
    assert meter.exhaustion_ratio == meter.exhaustion_ticks / meter.total_ticks


def test_residual_series_records_each_metered_tick() -> None:
    """The FR-INF-020 residual series has one sample per metered tick (within the window)."""
    session = _run_rtc_with_delay(16.0)
    assert len(session.meter.residual_series) == session.meter.total_ticks


def test_begin_episode_resets_the_meter() -> None:
    """Episode start clears the exhaustion counters (`FR-INF-066` / metering reset)."""
    session = _run_rtc_with_delay(32.0)
    assert session.meter.total_ticks > 0
    session.begin_episode()
    assert session.meter.total_ticks == 0
    assert session.meter.exhaustion_ticks == 0
    assert session.meter.residual_series == ()
