"""Dual-timestamp preservation (CG-3B-07 ②, `FR-TEL-022`) — a single stamp is the defect.

The source `t` (CLIENT clock, an age input) and the PC receive instant (SERVER
`CLOCK_MONOTONIC` ns) are both preserved and independent: the same source `t` under
two different receive instants yields two distinct receive stamps, and vice versa.
Collapsing the two into one would erase the only basis for latency measurement — so
the test asserts they never move together.
"""

from __future__ import annotations

import pytest

from backend.teleop.vr_udp import parse_datagram
from contracts.teleop import TeleopSample
from tests.wp3b07._support import datagram, raw_payload


def test_both_timestamps_preserved_distinctly() -> None:
    """A frame keeps the source `t` and the PC receive instant as separate fields."""
    frame = parse_datagram(datagram(raw_payload(source_ts=42.5)), receive_mono_ns=9_876_543_210)
    assert frame.source_ts == pytest.approx(42.5)
    assert frame.receive_mono_ns == 9_876_543_210
    # They are not the same number reused: source is float seconds, receive is int ns.
    assert frame.source_ts != frame.receive_mono_ns


def test_receive_instant_varies_under_fixed_source_ts() -> None:
    """The same source `t` received twice yields two different receive stamps."""
    payload = raw_payload(source_ts=1.0)
    first = parse_datagram(datagram(payload), receive_mono_ns=100)
    second = parse_datagram(datagram(payload), receive_mono_ns=200)
    assert first.source_ts == second.source_ts
    assert first.receive_mono_ns != second.receive_mono_ns


def test_source_ts_varies_under_fixed_receive_instant() -> None:
    """Two source times stamped at one receive instant keep both source values."""
    first = parse_datagram(datagram(raw_payload(source_ts=1.0)), receive_mono_ns=500)
    second = parse_datagram(datagram(raw_payload(source_ts=2.0)), receive_mono_ns=500)
    assert first.receive_mono_ns == second.receive_mono_ns
    assert first.source_ts != second.source_ts


def test_receive_instant_is_integer_nanoseconds() -> None:
    """The receive stamp is `CLOCK_MONOTONIC` integer ns, enforced by the contract."""
    frame = parse_datagram(datagram(raw_payload()), receive_mono_ns=123)
    assert isinstance(frame.receive_mono_ns, int)
    assert isinstance(frame.teleop_sample, TeleopSample)


def test_contract_rejects_float_receive_instant() -> None:
    """A non-integer receive instant is rejected — the server clock is monotonic ns."""
    with pytest.raises(ValueError):
        parse_datagram(datagram(raw_payload()), receive_mono_ns=1.5)  # type: ignore[arg-type]
