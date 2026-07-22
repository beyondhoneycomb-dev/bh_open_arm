"""A telemetry sample must be exactly the 8-joint × 8-channel matrix, or it is refused.

The dump's guarantee is that every joint and channel is present for every retained
tick; a ragged sample would let a later dump silently short a channel. The shape is
checked at construction so the failure is at the source, not at analysis time.
"""

from __future__ import annotations

import pytest

from backend.event_ring import (
    CHANNEL_COUNT,
    EVENT_JOINT_COUNT,
    EventChannel,
    EventRingShapeError,
    TelemetrySample,
)
from tests.wp2c09.conftest import encoded_sample


def test_correct_shape_is_accepted() -> None:
    """A full 8×8 sample constructs and reads back by joint and by channel."""
    sample = encoded_sample(tick=7)

    assert len(sample.rows) == EVENT_JOINT_COUNT
    assert len(sample.joint(0)) == CHANNEL_COUNT
    assert len(sample.channel(EventChannel.R)) == EVENT_JOINT_COUNT
    # Column slice picks the R column across joints: rows[j][R.column].
    assert sample.channel(EventChannel.R) == tuple(
        float(7 * 1000 + joint * 10 + EventChannel.R.column) for joint in range(EVENT_JOINT_COUNT)
    )


def test_wrong_joint_count_is_refused() -> None:
    """A sample missing a joint row is rejected at construction."""
    short = tuple((0.0,) * CHANNEL_COUNT for _ in range(EVENT_JOINT_COUNT - 1))
    with pytest.raises(EventRingShapeError):
        TelemetrySample(at=0.0, rows=short)


def test_wrong_channel_count_is_refused() -> None:
    """A sample missing a channel in any joint row is rejected at construction."""
    ragged = tuple(
        (0.0,) * (CHANNEL_COUNT - 1 if joint == 3 else CHANNEL_COUNT)
        for joint in range(EVENT_JOINT_COUNT)
    )
    with pytest.raises(EventRingShapeError):
        TelemetrySample(at=0.0, rows=ragged)
