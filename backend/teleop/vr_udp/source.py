"""`PoseSource` and the threaded UDP implementation for the Quest APK path.

`PoseSource` is the source-agnostic interface WP-3B-09/10 consume: the clutch,
smoother, IK and safety gates are the same whether poses arrive over UDP (this
module) or WebXR (WP-3B-08). It exposes the frozen `frame_applied` declaration and
a single non-blocking `read_latest()`.

`VrUdpPoseSource` binds the `:5006` datagram socket and runs one daemon thread that
receives, stamps the PC receive instant, parses and overwrites a single latest
snapshot. `read_latest()` reads only that snapshot and never touches the socket, so
`get_action()` calling it once per tick can never block on the network and can
never fall behind on a queue (`FR-TEL-005`, acceptance ④). A malformed datagram is
counted and dropped, never fatal to the thread.
"""

from __future__ import annotations

import socket
import threading
import time
from abc import ABC, abstractmethod
from types import TracebackType

from backend.teleop.vr_udp.constants import (
    FRAME_APPLIED,
    RECV_BUFFER_BYTES,
    RECV_POLL_TIMEOUT_S,
    UDP_HOST_DEFAULT,
    UDP_PORT_DEFAULT,
)
from backend.teleop.vr_udp.frame import VrFrame
from backend.teleop.vr_udp.protocol import FrameParseError, parse_datagram, split_frames


class PoseSource(ABC):
    """The source-agnostic VR pose interface WP-3B-09/10 consume.

    A pose source runs its own reception (out of the control loop's way) and offers
    the latest sample as a non-blocking snapshot. It also declares whether the
    robot-world frame transform has already been applied, so a consumer never
    applies it twice.
    """

    @property
    @abstractmethod
    def frame_applied(self) -> bool:
        """Whether this source already applied the `R_ROBOT` world-frame transform."""

    @abstractmethod
    def start(self) -> None:
        """Begin reception (idempotent per source lifecycle)."""

    @abstractmethod
    def stop(self) -> None:
        """End reception and release resources."""

    @abstractmethod
    def read_latest(self) -> VrFrame | None:
        """Return the most recent frame without blocking, or None if none yet."""


class VrUdpPoseSource(PoseSource):
    """A UDP `:5006` pose source: one receive thread, one latest snapshot.

    Ownership/threading: `start()` spawns a single daemon thread that is the sole
    writer of the snapshot; `read_latest()` (the control loop) is the reader. The
    snapshot is a single reference guarded by a lock — there is no queue, so a slow
    reader drops intermediate frames rather than accumulating latency.
    """

    def __init__(self, host: str = UDP_HOST_DEFAULT, port: int = UDP_PORT_DEFAULT) -> None:
        """Configure the bind address without opening the socket yet.

        Args:
            host: Bind host; tests pass `"127.0.0.1"`.
            port: Bind port; tests pass `0` for an ephemeral port.
        """
        self._host = host
        self._port = port
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: VrFrame | None = None
        self._received_frames = 0
        self._malformed_frames = 0
        self._bound_port: int | None = None

    @property
    def frame_applied(self) -> bool:
        """True — this source applies the `R_ROBOT` transform; do not re-apply it."""
        return FRAME_APPLIED

    @property
    def bound_port(self) -> int | None:
        """The actually-bound port (resolves an ephemeral `0`), or None before start."""
        return self._bound_port

    @property
    def received_frames(self) -> int:
        """The count of well-formed frames accepted since start."""
        with self._lock:
            return self._received_frames

    @property
    def malformed_frames(self) -> int:
        """The count of datagrams dropped as malformed since start."""
        with self._lock:
            return self._malformed_frames

    def ingest(self, data: bytes, receive_mono_ns: int) -> int:
        """Parse a datagram's frames and overwrite the latest snapshot.

        Shared by the receive thread and by tests that feed bytes without a socket.
        Every frame in one datagram shares the receive instant, since they arrived
        together. A malformed frame is counted and skipped.

        Args:
            data: Raw datagram bytes (one or more newline-terminated frames).
            receive_mono_ns: The PC receive instant stamped on arrival.

        Returns:
            (int) The number of well-formed frames accepted from this datagram.
        """
        accepted = 0
        for segment in split_frames(data):
            try:
                frame = parse_datagram(segment, receive_mono_ns)
            except FrameParseError:
                with self._lock:
                    self._malformed_frames += 1
                continue
            with self._lock:
                self._latest = frame
                self._received_frames += 1
            accepted += 1
        return accepted

    def read_latest(self) -> VrFrame | None:
        """Return the most recent frame snapshot without blocking.

        Touches only the in-memory snapshot, never the socket, so the control loop
        can call this once per tick with no risk of blocking on the network.

        Returns:
            (VrFrame | None) The latest frame, or None if none has arrived.
        """
        with self._lock:
            return self._latest

    def start(self) -> None:
        """Open and bind the UDP socket and spawn the receive thread.

        Raises:
            RuntimeError: If the source is already started.
        """
        if self._thread is not None:
            raise RuntimeError("VrUdpPoseSource already started")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._host, self._port))
        sock.settimeout(RECV_POLL_TIMEOUT_S)
        self._socket = sock
        self._bound_port = sock.getsockname()[1]
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="vr-udp-receiver", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """Receive, stamp, parse and snapshot until stopped (receive thread)."""
        sock = self._socket
        assert sock is not None  # start() sets it before spawning this thread
        while not self._stop.is_set():
            try:
                data, _ = sock.recvfrom(RECV_BUFFER_BYTES)
            except TimeoutError:
                continue
            except OSError:
                # The socket was closed under us by stop(); exit the loop cleanly.
                break
            self.ingest(data, time.monotonic_ns())

    def stop(self) -> None:
        """Signal the thread, close the socket and join.

        Safe to call when never started or already stopped.
        """
        self._stop.set()
        if self._socket is not None:
            self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=RECV_POLL_TIMEOUT_S * 5)
        self._thread = None
        self._socket = None

    def __enter__(self) -> VrUdpPoseSource:
        """Start the source for use as a context manager."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop the source on context exit."""
        self.stop()
