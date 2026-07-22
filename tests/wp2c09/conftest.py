"""Shared telemetry builders for the WP-2C-09 event-ring and monitor tests.

Two builders serve the two acceptance claims. `encoded_sample` stamps every cell
with a value derived from its `(tick, joint, channel)` coordinate, so a dump can be
checked for loss and corruption by exact content — a missing or reordered sample is
visible, not merely a wrong count. `uniform_sample` fills a chosen residual and
temperature across all joints for driving the model-error monitor.

The synthetic loop rate here is a test rate, not the on-hardware rate (1 kHz, or the
≤625 Hz pattern-B clamp of NFR-SAF-001), which is deferred to `reverify`.
"""

from __future__ import annotations

from backend.event_ring import CHANNEL_COUNT, EVENT_JOINT_COUNT, EventChannel, TelemetrySample

SAMPLE_RATE_HZ = 100
DT_SEC = 1.0 / SAMPLE_RATE_HZ


def encoded_sample(tick: int) -> TelemetrySample:
    """Build a sample whose every cell encodes its own `(tick, joint, channel)`.

    Args:
        tick: The tick index; also fixes `at = tick · DT_SEC`.

    Returns:
        (TelemetrySample) A sample where `rows[j][c] == tick*1000 + j*10 + c`, so a
        dropped or reordered sample fails an exact-content comparison.
    """
    rows = tuple(
        tuple(float(tick * 1000 + joint * 10 + channel) for channel in range(CHANNEL_COUNT))
        for joint in range(EVENT_JOINT_COUNT)
    )
    return TelemetrySample(at=tick * DT_SEC, rows=rows)


def uniform_sample(
    at: float,
    *,
    residual_nm: float,
    t_mos_degc: float = 30.0,
    t_rotor_degc: float = 25.0,
) -> TelemetrySample:
    """Build a sample with one residual and temperature applied to every joint.

    Args:
        at: Monotonic timestamp, seconds.
        residual_nm: The `r` value every joint carries, newton-metres.
        t_mos_degc: The drive temperature every joint carries.
        t_rotor_degc: The rotor temperature every joint carries.

    Returns:
        (TelemetrySample) The filled sample; unnamed channels are zero.
    """
    rows = []
    for _joint in range(EVENT_JOINT_COUNT):
        values = [0.0] * CHANNEL_COUNT
        values[EventChannel.R.column] = residual_nm
        values[EventChannel.T_MOS.column] = t_mos_degc
        values[EventChannel.T_ROTOR.column] = t_rotor_degc
        rows.append(tuple(values))
    return TelemetrySample(at=at, rows=tuple(rows))
