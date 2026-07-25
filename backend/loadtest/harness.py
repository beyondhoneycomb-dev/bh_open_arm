"""The synthetic single-WS load harness — a deterministic model of one WebSocket.

U-4 keeps one WebSocket (D-2 is not resumed): telemetry, command, camera-binary and
the dead-man lease all multiplex over a single socket, so a large JPEG frame can put
a control message at the back of the line — head-of-line blocking is structural. This
harness reproduces that one channel and measures what happens to the control classes
when the camera load saturates the link.

It does not fork the transport rules. The frame priorities, the backpressure signal
(`bufferedAmount`), its threshold, and which classes are shed versus protected are all
read from `CTR-WS@v1` (`contracts.ws.schema`), and camera load is sized from the
`06` §2.9 bandwidth formula (`backend.camera.bandwidth`). The only thing this module
adds is the discrete-event drain: one bounded send buffer, drained in priority order
each step, with camera frames shed on the exact `should_drop_under_backpressure` rule
the frontend `WsClient` uses.

Determinism is the point (like the actuation fault harness): time advances by a fixed
step, traffic is generated at fixed rates, and no wall clock or randomness enters — so
"the tail latency of the command class at this load" is a reproducible fact.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from backend.camera.bandwidth import descriptor_bandwidth_mbps
from backend.camera.constants import BITS_PER_BYTE, MEGABIT_DIVISOR
from backend.camera.descriptor import CameraDescriptor
from backend.loadtest.constants import (
    CLIENT_LOCALITY_LAN,
    JPEG_PREVIEW_COMPRESSION_RATIO,
    WS_PUBLISH_RATE_DEFAULT_HZ,
)
from contracts.ws.schema import (
    FRAME_TABLE,
    WsFrameType,
    should_drop_under_backpressure,
)

# Small text frames on the wire. These are load-model sizes for the control classes,
# not spec constants: a joint-state telemetry frame and a command frame are a few
# hundred bytes of JSON, and a lease renewal is smaller still. Their exact size does
# not move the ordering result — the camera class is three to four orders of magnitude
# larger — but they must be non-zero so the control classes consume real link budget.
TELEMETRY_FRAME_BYTES = 2048
COMMAND_FRAME_BYTES = 512
LEASE_FRAME_BYTES = 128

# The default simulated step. One millisecond is fine-grained enough to place a drain
# event without the per-step byte budget swamping a whole camera frame in one tick.
DEFAULT_STEP_SEC = 0.001

# The lease renewal cadence the client drives (`frontend` LeaseRenewer default is
# 250 ms). Renewals are tiny and highest priority, so they never queue behind camera.
DEFAULT_LEASE_RENEW_HZ = 4.0

# A command cadence for the synthetic operator. Commands are client-authored and
# bursty in reality; a steady rate is the conservative model for a load test because
# it keeps the control class continuously present in the queue.
DEFAULT_COMMAND_HZ = 20.0


def _uncompressed_bytes_per_sec(descriptor: CameraDescriptor) -> float:
    """Return one camera's uncompressed wire rate, from the `06` §2.9 budget (bytes/s).

    Reuses `backend.camera.bandwidth` for the Mbps figure rather than re-deriving
    `W×H×Bpp×8×fps`, then converts megabits-per-second to bytes-per-second.

    Args:
        descriptor: The camera whose active profiles define its rate.

    Returns:
        (float) Uncompressed bytes per second across the camera's active profiles.
    """
    return descriptor_bandwidth_mbps(descriptor) * MEGABIT_DIVISOR / BITS_PER_BYTE


def _camera_max_fps(descriptor: CameraDescriptor) -> int:
    """Return the highest fps among a camera's active profiles (its preview cadence)."""
    return max(profile.fps for profile in descriptor.profiles)


@dataclass(frozen=True)
class LoadProfile:
    """One synthetic load configuration: what traffic to generate and over what link.

    Attributes:
        cameras: The camera descriptors whose preview streams flood the link. Sized
            via the `06` §2.9 bandwidth budget; a max-load run uses many high-res
            cameras (e.g. `backend.camera.fixtures.d415_quad_full_res`).
        client_count: How many browser clients each receive the camera streams. The
            single-WS load scales with clients, so this is the "multi-client" axis.
        telemetry_hz: Joint-state publish rate per client (default 30 Hz per
            `NFR-GUI-003`).
        command_hz: Command frames issued per client per second.
        lease_renew_hz: Dead-man renewals per client per second.
        locality: `localhost` or `lan` — a report label; a localhost run that never
            saturates does not stand in for a LAN run (`NFR-GUI-012`).
        link_capacity_bytes_per_sec: The one WS link's throughput ceiling. At max load
            the camera sum exceeds this and the link saturates.
    """

    cameras: tuple[CameraDescriptor, ...]
    client_count: int
    link_capacity_bytes_per_sec: float
    telemetry_hz: float = WS_PUBLISH_RATE_DEFAULT_HZ
    command_hz: float = DEFAULT_COMMAND_HZ
    lease_renew_hz: float = DEFAULT_LEASE_RENEW_HZ
    locality: str = CLIENT_LOCALITY_LAN

    def camera_preview_bytes_per_sec(self) -> float:
        """Return the aggregate JPEG preview rate across all cameras and clients.

        The uncompressed `06` §2.9 rate is divided by the JPEG preview ratio (previews
        are lossy, `NFR-GUI-012`), then multiplied by the client count — every client
        pulls the same preview streams over the single WS.

        Returns:
            (float) Aggregate camera preview bytes per second offered to the link.
        """
        per_client = sum(_uncompressed_bytes_per_sec(cam) for cam in self.cameras)
        return per_client / JPEG_PREVIEW_COMPRESSION_RATIO * self.client_count

    def is_saturating(self) -> bool:
        """Whether the offered camera preview load alone exceeds the link capacity.

        Returns:
            (bool) True when the camera sum is over the link ceiling — the regime the
            HOL judge must be exercised in (a run that never saturates proves nothing).
        """
        return self.camera_preview_bytes_per_sec() > self.link_capacity_bytes_per_sec


@dataclass(frozen=True)
class _PendingFrame:
    """One frame queued in the send buffer, remembering when it was offered."""

    frame_type: WsFrameType
    size_bytes: int
    enqueued_at: float


@dataclass
class ClassResult:
    """The measured outcome for one frame class over a run.

    Attributes:
        frame_type: The class this result describes.
        latencies_sec: Transport (queueing) delay of every delivered frame, seconds.
        delivered: Count of frames that reached the client.
        dropped: Count of frames shed under backpressure before delivery.
    """

    frame_type: WsFrameType
    latencies_sec: list[float] = field(default_factory=list)
    delivered: int = 0
    dropped: int = 0

    @property
    def offered(self) -> int:
        """Total frames offered to the link (delivered plus dropped)."""
        return self.delivered + self.dropped


@dataclass(frozen=True)
class LoadRun:
    """The result of one synthetic load run: per-class latency and drop outcomes.

    Attributes:
        profile: The load configuration that produced this run.
        duration_sec: Simulated wall time the run covered.
        results: One `ClassResult` per frame class that carried traffic.
        peak_buffered_bytes: The highest send-buffer occupancy observed — the value
            the backpressure signal peaked at.
    """

    profile: LoadProfile
    duration_sec: float
    results: dict[WsFrameType, ClassResult]
    peak_buffered_bytes: int

    def result(self, frame_type: WsFrameType) -> ClassResult:
        """Return the class result for a frame type, empty if it carried no traffic."""
        return self.results.get(frame_type, ClassResult(frame_type=frame_type))


class _SendBuffer:
    """The single WS send buffer: one serialized writer, frames selected lease-first.

    Priorities, the drop-under-backpressure rule and the protected set are all read
    from `CTR-WS@v1`; this buffer only sequences them. `bufferedAmount` is the total
    unsent bytes (queued plus the in-flight frame's remainder), which is exactly what
    the frontend `WsClient` reads to decide a camera shed, so the same rule fires here
    on the same signal.

    The link is one serialized byte stream, so a frame is chosen by priority but not
    preempted once its bytes start going out — a large camera frame already on the
    wire holds the line until its last byte, which is the residual head-of-line the
    single WS carries by construction (U-4). Backpressure keeps that to at most one
    in-flight camera frame by shedding the rest, so a protected frame waits behind one
    frame at worst, never behind a whole camera backlog.
    """

    def __init__(self) -> None:
        """Create an empty per-class buffer, ordered by the CTR-WS priority classes."""
        self._queues: dict[WsFrameType, deque[_PendingFrame]] = {
            frame_type: deque() for frame_type in WsFrameType
        }
        self._queued_bytes = 0
        self._current: _PendingFrame | None = None
        self._current_remaining = 0
        self._peak_buffered_bytes = 0
        # Selection order is ascending priority (lease = 0 first), read from the frame
        # table so the ordering has one definition point — the contract, not here.
        self._drain_order = sorted(WsFrameType, key=lambda ft: int(FRAME_TABLE[ft].priority))

    @property
    def buffered_bytes(self) -> int:
        """Current unsent bytes — the `bufferedAmount` backpressure signal."""
        return self._queued_bytes + self._current_remaining

    @property
    def peak_buffered_bytes(self) -> int:
        """The highest buffered-bytes level seen over the run."""
        return self._peak_buffered_bytes

    def offer(self, frame: _PendingFrame) -> bool:
        """Offer a frame to the buffer, shedding it if backpressure rejects it.

        The shed decision is `CTR-WS@v1`'s `should_drop_under_backpressure` read
        against the current buffered bytes: only a camera frame over threshold is
        shed; lease, command and telemetry are always admitted.

        Args:
            frame: The frame offered this step.

        Returns:
            (bool) True if the frame was queued, False if it was shed.
        """
        if should_drop_under_backpressure(frame.frame_type, self.buffered_bytes):
            return False
        self._queues[frame.frame_type].append(frame)
        self._queued_bytes += frame.size_bytes
        self._peak_buffered_bytes = max(self._peak_buffered_bytes, self.buffered_bytes)
        return True

    def _select_next(self) -> None:
        """Promote the highest-priority queued frame to the in-flight slot."""
        for frame_type in self._drain_order:
            queue = self._queues[frame_type]
            if queue:
                frame = queue.popleft()
                self._queued_bytes -= frame.size_bytes
                self._current = frame
                self._current_remaining = frame.size_bytes
                return
        self._current = None
        self._current_remaining = 0

    def drain(self, byte_budget: int, now: float) -> list[tuple[_PendingFrame, float]]:
        """Send up to `byte_budget` bytes this step, returning fully delivered frames.

        Bytes are sent from the in-flight frame first, then the next is selected by
        priority; a frame larger than one step's budget spans steps. A frame is
        delivered — and its transport latency recorded — only when its last byte goes
        out.

        Args:
            byte_budget: Bytes the link can carry this step.
            now: The current simulated time, stamped as the delivery instant.

        Returns:
            (list[tuple[_PendingFrame, float]]) Delivered frames with their transport
            latency (delivery time minus enqueue time).
        """
        delivered: list[tuple[_PendingFrame, float]] = []
        available = byte_budget
        while available > 0:
            if self._current is None:
                self._select_next()
                if self._current is None:
                    break
            sent = min(available, self._current_remaining)
            available -= sent
            self._current_remaining -= sent
            if self._current_remaining == 0:
                delivered.append((self._current, now - self._current.enqueued_at))
                self._current = None
        return delivered


def _class_bytes(frame_type: WsFrameType) -> int:
    """Return the modelled wire size of a control-class frame."""
    if frame_type is WsFrameType.TELEMETRY:
        return TELEMETRY_FRAME_BYTES
    if frame_type is WsFrameType.COMMAND:
        return COMMAND_FRAME_BYTES
    return LEASE_FRAME_BYTES


def _due(rate_hz: float, step_index: int, step_sec: float) -> int:
    """Return how many events of a fixed-rate stream fall in step `step_index`.

    Uses the difference of cumulative counts so a rate that is not a multiple of the
    step frequency still averages out exactly rather than rounding every step to zero.

    Args:
        rate_hz: The stream's frequency.
        step_index: The 0-based step being generated.
        step_sec: The step duration.

    Returns:
        (int) Events that become due during this step.
    """
    before = int(rate_hz * step_sec * step_index)
    after = int(rate_hz * step_sec * (step_index + 1))
    return after - before


def run_load(
    profile: LoadProfile,
    duration_sec: float,
    step_sec: float = DEFAULT_STEP_SEC,
) -> LoadRun:
    """Run the synthetic single-WS load and return per-class latency and drop outcomes.

    Each step: generate this step's telemetry, command, lease and camera frames (per
    client), offer them to the one send buffer (camera frames subject to the CTR-WS
    backpressure shed), then drain the buffer up to the link's per-step byte budget in
    priority order. Delivered frames record their transport latency.

    Args:
        profile: The load configuration.
        duration_sec: Simulated seconds to run.
        step_sec: The simulated step; smaller resolves latency finer.

    Returns:
        (LoadRun) The per-class results and the peak buffer occupancy.

    Raises:
        ValueError: If `duration_sec` or `step_sec` is not positive.
    """
    if duration_sec <= 0.0 or step_sec <= 0.0:
        raise ValueError("duration_sec and step_sec must be positive")

    buffer = _SendBuffer()
    results: dict[WsFrameType, ClassResult] = {
        frame_type: ClassResult(frame_type=frame_type)
        for frame_type in (
            WsFrameType.LEASE_RENEW,
            WsFrameType.COMMAND,
            WsFrameType.TELEMETRY,
            WsFrameType.CAMERA,
        )
    }
    byte_budget = int(profile.link_capacity_bytes_per_sec * step_sec)
    step_count = int(round(duration_sec / step_sec))

    control_streams = (
        (WsFrameType.LEASE_RENEW, profile.lease_renew_hz),
        (WsFrameType.COMMAND, profile.command_hz),
        (WsFrameType.TELEMETRY, profile.telemetry_hz),
    )
    camera_streams = tuple(
        (
            int(round(_uncompressed_bytes_per_sec(cam) / JPEG_PREVIEW_COMPRESSION_RATIO
                      / _camera_max_fps(cam))),
            _camera_max_fps(cam),
        )
        for cam in profile.cameras
    )

    for step_index in range(step_count):
        now = step_index * step_sec
        for frame_type, rate_hz in control_streams:
            count = _due(rate_hz, step_index, step_sec) * profile.client_count
            for _ in range(count):
                frame = _PendingFrame(frame_type, _class_bytes(frame_type), now)
                _record_offer(results[frame_type], buffer.offer(frame))
        for frame_bytes, fps in camera_streams:
            count = _due(fps, step_index, step_sec) * profile.client_count
            for _ in range(count):
                frame = _PendingFrame(WsFrameType.CAMERA, frame_bytes, now)
                _record_offer(results[WsFrameType.CAMERA], buffer.offer(frame))

        for frame, latency in buffer.drain(byte_budget, now + step_sec):
            result = results[frame.frame_type]
            result.delivered += 1
            result.latencies_sec.append(latency)

    return LoadRun(
        profile=profile,
        duration_sec=duration_sec,
        results=results,
        peak_buffered_bytes=buffer.peak_buffered_bytes,
    )


def _record_offer(result: ClassResult, admitted: bool) -> None:
    """Count a shed frame as a drop; a queued frame is counted on delivery."""
    if not admitted:
        result.dropped += 1
