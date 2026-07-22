"""Acceptance ④ (CG-3B-07d) — `get_action` reads only the latest snapshot.

`FR-TEL-005`: reception is a separate thread; the read side is non-blocking and
sees only the most recent sample, never a queue backlog. This covers both the
in-memory snapshot (fed directly, no socket) and the real threaded socket path —
bind loopback on an ephemeral port, send a datagram, and observe the receive thread
overwrite the snapshot that `read_latest()` returns.
"""

from __future__ import annotations

import socket
import time

import pytest

from backend.teleop.vr_udp import VrUdpPoseSource
from contracts.fixtures.vr_pose_stream import SyntheticVrPoseStream
from tests.wp3b07._support import datagram, datagram_from_sample, raw_payload

_DEADLINE_S = 2.0
_POLL_S = 0.005


def test_read_latest_is_none_before_any_frame() -> None:
    """With nothing received, the snapshot read returns None rather than blocking."""
    source = VrUdpPoseSource()
    assert source.read_latest() is None


def test_ingest_updates_snapshot_latest_wins() -> None:
    """Feeding frames advances the snapshot to the most recent one (no backlog)."""
    source = VrUdpPoseSource()
    stream = SyntheticVrPoseStream()
    for index in range(5):
        source.ingest(datagram_from_sample(stream, index), receive_mono_ns=index)
    latest = source.read_latest()
    assert latest is not None
    assert latest.source_ts == stream.sample(4).teleop_sample.source_ts
    assert source.received_frames == 5


def test_packed_datagram_leaves_only_the_last_frame() -> None:
    """Several frames in one datagram: the snapshot holds the last, not a queue."""
    source = VrUdpPoseSource()
    stream = SyntheticVrPoseStream()
    packed = b"".join(datagram_from_sample(stream, i) for i in range(3))
    accepted = source.ingest(packed, receive_mono_ns=1)
    assert accepted == 3
    latest = source.read_latest()
    assert latest is not None
    assert latest.source_ts == stream.sample(2).teleop_sample.source_ts


def test_malformed_datagram_counted_not_snapshotted() -> None:
    """A malformed datagram bumps the drop counter and leaves the snapshot intact."""
    source = VrUdpPoseSource()
    source.ingest(datagram(raw_payload(source_ts=1.0)), receive_mono_ns=1)
    good = source.read_latest()
    source.ingest(b"garbage not json\n", receive_mono_ns=2)
    assert source.read_latest() is good  # unchanged reference
    assert source.malformed_frames == 1
    assert source.received_frames == 1


def test_threaded_socket_receive_updates_snapshot() -> None:
    """The real receive thread binds `:0`, parses a sent datagram, updates the snapshot."""
    source = VrUdpPoseSource(host="127.0.0.1", port=0)
    source.start()
    try:
        port = source.bound_port
        assert port is not None
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            client.sendto(datagram(raw_payload(source_ts=3.25)), ("127.0.0.1", port))
        finally:
            client.close()

        deadline = time.monotonic() + _DEADLINE_S
        latest = source.read_latest()
        while latest is None and time.monotonic() < deadline:
            time.sleep(_POLL_S)
            latest = source.read_latest()

        assert latest is not None
        assert latest.source_ts == 3.25
        assert latest.receive_mono_ns > 0  # stamped by the receive thread, not the sender
    finally:
        source.stop()


def test_context_manager_starts_and_stops() -> None:
    """The source works as a context manager: bound inside, torn down on exit."""
    with VrUdpPoseSource(host="127.0.0.1", port=0) as source:
        assert source.bound_port is not None
    # After exit the thread is joined and the socket released; a re-start rebinds.
    source.start()
    assert source.bound_port is not None
    source.stop()


def test_double_start_is_rejected() -> None:
    """Starting an already-started source is a programming error, surfaced loudly."""
    source = VrUdpPoseSource(host="127.0.0.1", port=0)
    source.start()
    try:
        with pytest.raises(RuntimeError):
            source.start()
    finally:
        source.stop()
