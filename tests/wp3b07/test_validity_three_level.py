"""Acceptance ②/③ (CG-3B-07b/c) — three-level validity, exposed per arm.

`FR-TEL-021`: the OK/STALE/INVALID model is exposed per arm. STALE still publishes
its pose; INVALID withholds the pose (`05` §2.14) while still surfacing the INVALID
state so the downstream smoother can reset on the INVALID->valid transition. The
overall and per-arm validity come from the distinct wire fields `v`/`vl`/`vr`.
"""

from __future__ import annotations

import pytest

from backend.teleop.vr_udp import parse_datagram
from backend.teleop.vr_udp.protocol import FrameParseError
from contracts.fixtures.vr_pose_stream import SyntheticVrPoseStream
from contracts.teleop import TeleopValidity
from tests.wp3b07._support import datagram, datagram_from_sample, raw_payload


def _parse(payload: dict[str, object]):
    return parse_datagram(datagram(payload), receive_mono_ns=1)


def test_ok_publishes_pose() -> None:
    """An OK arm carries a transformed pose and is publishable."""
    frame = _parse(raw_payload(validity=TeleopValidity.OK))
    assert frame.validity is TeleopValidity.OK
    assert frame.is_publishable is True
    assert frame.arm("left").world_pose is not None
    assert frame.arm("left").is_publishable is True


def test_stale_still_publishes_pose() -> None:
    """A STALE arm still publishes its pose (the last pose passes through)."""
    frame = _parse(raw_payload(validity=TeleopValidity.STALE))
    assert frame.validity is TeleopValidity.STALE
    assert frame.is_publishable is True
    assert frame.arm("right").validity is TeleopValidity.STALE
    assert frame.arm("right").world_pose is not None


def test_invalid_withholds_pose_but_exposes_state() -> None:
    """An INVALID arm withholds its pose yet still reports INVALID for reset logic."""
    frame = _parse(raw_payload(validity=TeleopValidity.INVALID))
    assert frame.validity is TeleopValidity.INVALID
    assert frame.is_publishable is False
    assert frame.arm("left").validity is TeleopValidity.INVALID
    assert frame.arm("left").world_pose is None
    assert frame.arm("left").is_publishable is False


def test_per_arm_validity_is_independent() -> None:
    """`vl` and `vr` are exposed independently: one arm OK while the other is INVALID."""
    frame = _parse(
        raw_payload(
            validity=TeleopValidity.OK,
            left_validity=TeleopValidity.OK,
            right_validity=TeleopValidity.INVALID,
        )
    )
    assert frame.arm("left").validity is TeleopValidity.OK
    assert frame.arm("left").world_pose is not None
    assert frame.arm("right").validity is TeleopValidity.INVALID
    assert frame.arm("right").world_pose is None


def test_stale_arm_under_ok_overall() -> None:
    """A per-arm STALE while the overall frame is OK is surfaced on that arm alone."""
    frame = _parse(
        raw_payload(
            validity=TeleopValidity.OK,
            left_validity=TeleopValidity.STALE,
            right_validity=TeleopValidity.OK,
        )
    )
    assert frame.validity is TeleopValidity.OK
    assert frame.arm("left").validity is TeleopValidity.STALE
    assert frame.arm("left").world_pose is not None  # STALE publishes


def test_injected_invalid_index_from_fixture() -> None:
    """The fixture's injectable INVALID index parses to a withheld pose."""
    stream = SyntheticVrPoseStream(invalid_indices=frozenset({4}))
    frame = parse_datagram(datagram_from_sample(stream, 4), receive_mono_ns=1)
    assert frame.validity is TeleopValidity.INVALID
    assert frame.arm("left").world_pose is None
    assert frame.arm("right").world_pose is None


@pytest.mark.parametrize("bad", [3, -1, 99])
def test_validity_outside_domain_rejected(bad: int) -> None:
    """A validity wire value outside 0/1/2 is a malformed frame."""
    payload = raw_payload()
    payload["v"] = bad
    with pytest.raises(FrameParseError):
        _parse(payload)
