"""The TX-only WebSocket side of the preview pipe (WP-3B-06).

The preview is TX-only on the WS: it pushes binary frames out and never reads a
command back. That is why this sink has exactly two methods — one to report the
send-buffer level so the pipe can shed under backpressure, one to send a binary
frame — and no method through which a robot command could travel. The preview
pipe holds a `PreviewSink` and nothing wider, so "the preview does not drive the
robot" (`02b` §6.2 acceptance, the `FAIL_BLOCKING` boundary) is enforced by the
shape of the surface, not by discipline.

The sink is the one realtime channel (`CTR-WS@v1` D-2): a preview frame rides the
same single WebSocket as telemetry and the lease, and is the first class shed when
the buffer fills. There is no second stream — the parallel realtime stacks
`CTR-WS@v1` forbids (`FORBIDDEN_PARALLEL_STACKS`) are opened nowhere in this
package (`02b` §6.2 acceptance ④).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PreviewSink(Protocol):
    """The single-WebSocket transmit surface a preview frame is sent through.

    `buffered_amount()` mirrors the WebSocket `bufferedAmount` the `CTR-WS@v1`
    backpressure rule reads: when it is over threshold the pipe drops the camera
    frame rather than encoding and queuing it, so a saturated link never delays a
    dead-man renewal (HOL mitigation). `send_binary()` is the only egress, and it
    carries opaque bytes — a packed preview frame — never a structured command.
    """

    def buffered_amount(self) -> int: ...

    def send_binary(self, data: bytes) -> None: ...
