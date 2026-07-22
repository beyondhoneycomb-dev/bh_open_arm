"""Acceptance ② + frozen contract: slop floor forced, arrival-time fallbacks off.

`02b` §6.2 WP-3B-04: `slop` is forced at or above the half-frame phase bound (a slop
under it drops out-of-phase frames), and `allow_headerless`/`sync_arrival_time` are
disabled by default because arrival time is not a matching basis. These tests pin the
floor derivation, its enforcement, and the disabled fallbacks.
"""

from __future__ import annotations

import pytest

from backend.sensing.timesync.constants import NANOS_PER_SECOND
from backend.sensing.timesync.policy import (
    SyncPolicy,
    SyncPolicyError,
    default_queue_size,
    slop_floor_ns,
)
from contracts.capture.schema import CAPTURE_MATCH_QUEUE
from tests.wp3b04.conftest import configured_spec, spec_fps

_FPS = spec_fps(configured_spec(0))


def test_slop_floor_is_half_a_frame_interval() -> None:
    """The floor at fps is half the frame period — 16.67 ms at 30 fps (②)."""
    assert slop_floor_ns(_FPS) == (NANOS_PER_SECOND // _FPS) // 2


def test_default_slop_takes_the_floor_exactly() -> None:
    """A policy built for an fps with no explicit slop sits on the floor."""
    policy = SyncPolicy.for_fps(_FPS)
    assert policy.slop_ns == slop_floor_ns(_FPS)


def test_a_slop_below_the_floor_is_refused() -> None:
    """A slop under the half-frame phase bound is rejected, not silently clamped (②)."""
    with pytest.raises(SyncPolicyError, match="phase floor"):
        SyncPolicy.for_fps(_FPS, slop_ns=slop_floor_ns(_FPS) - 1)


def test_a_slop_above_the_floor_is_kept() -> None:
    """A slop at or above the floor is honoured as configured."""
    generous = slop_floor_ns(_FPS) * 2
    assert SyncPolicy.for_fps(_FPS, slop_ns=generous).slop_ns == generous


def test_queue_size_defaults_to_the_frozen_capture_match_capacity() -> None:
    """The buffer bound comes from CTR-PRIM's capture_match queue, not a new number."""
    assert default_queue_size() == CAPTURE_MATCH_QUEUE.bounded_capacity
    assert SyncPolicy.for_fps(_FPS).queue_size == CAPTURE_MATCH_QUEUE.bounded_capacity


def test_arrival_time_fallbacks_are_off_by_default() -> None:
    """Both librealsense arrival-time fallbacks default to disabled (frozen contract)."""
    policy = SyncPolicy.for_fps(_FPS)
    assert policy.allow_headerless is False
    assert policy.sync_arrival_time is False


def test_enabling_allow_headerless_is_refused() -> None:
    """Turning on the headerless arrival-time fallback is a contract violation."""
    with pytest.raises(SyncPolicyError, match="arrival time"):
        SyncPolicy(
            slop_ns=slop_floor_ns(_FPS), queue_size=default_queue_size(), allow_headerless=True
        )


def test_enabling_sync_arrival_time_is_refused() -> None:
    """Turning on arrival-time matching is a contract violation."""
    with pytest.raises(SyncPolicyError, match="arrival time"):
        SyncPolicy(
            slop_ns=slop_floor_ns(_FPS), queue_size=default_queue_size(), sync_arrival_time=True
        )


def test_non_positive_fps_has_no_slop_floor() -> None:
    """A zero or negative fps cannot define a phase floor."""
    with pytest.raises(SyncPolicyError):
        slop_floor_ns(0)
