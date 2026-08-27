"""One frame from one camera, encoded for a browser, for the operator deciding which is which.

The device panel's whole mechanism is the picture: two Arducam B0495 that report one serial are
separated by the port, and the port is what the assignment is keyed on — but a port string does
not tell an operator which arm it is bolted to. The frame does.

**A snapshot is not a stream, and the difference is the point.** A slot's real stream belongs to
the capture run and the realtime channel. Opening a second reader over the same node while a run
is going takes frames the run is counting, and the run has no way to tell that from a camera that
started dropping. So this opens, reads, and closes — and when the node is already held, it says
so rather than waiting, because during a run "busy" is the correct and permanent answer.

The device is opened at whatever format it defaults to. The declared format belongs to the SLOT,
and a device with no slot yet has none — demanding one would make the cameras that most need
identifying the ones that cannot be previewed.

`cv2` is imported inside the call: it ships in the `robot` extra and this tree is imported by
callers that do not install it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from backend.camera.portpath import CaptureNode, node_by_port
from backend.camera.v4l2_source import CaptureDevice, open_v4l2_capture

# Frames read before the one that is kept. A capture hands back its buffered frames first, and on
# this bench those carry the previous exposure — the panel would show the scene from whenever the
# device was last opened, which for an identification is the one thing it must not do.
SNAPSHOT_WARMUP_FRAMES = 3

# JPEG quality for the preview. High enough that two similar scenes are distinguishable, low
# enough that a poll every few hundred milliseconds is not the reason the loop is slow.
JPEG_QUALITY = 70


class SnapshotUnavailableError(RuntimeError):
    """The device is there but would not hand over a frame."""


def grab_jpeg(
    nodes: Sequence[CaptureNode],
    port_path: str,
    open_capture: Callable[[str], CaptureDevice] | None = None,
) -> bytes:
    """Open the camera on `port_path`, take one frame, close it, and answer it as JPEG.

    Args:
        nodes: The capture nodes present now.
        port_path: The port of the camera to look at.
        open_capture: How to open the device, injected so the route is drivable with no camera.
            None uses cv2's V4L2 backend.

    Returns:
        (bytes) One JPEG frame.

    Raises:
        AmbiguousCameraPortError: If the present set does not distinguish its ports.
        CameraPortError: If nothing is on that port.
        SnapshotUnavailableError: If the device does not open, hands back no frame, or the frame
            does not encode. Held-by-a-run is the common case and is not distinguishable from a
            device that failed, so both arrive here — the message says which is likely.
    """
    import cv2

    node = node_by_port(nodes, port_path)
    opener = open_v4l2_capture if open_capture is None else open_capture
    capture = opener(str(node.device))
    try:
        if not capture.isOpened():
            raise SnapshotUnavailableError(
                f"{node.card} at {port_path} ({node.device}) did not open. A capture run holds "
                "its cameras for the whole window, and that is what this looks like."
            )
        frame = None
        for _ in range(SNAPSHOT_WARMUP_FRAMES + 1):
            ok, read = capture.read()
            if ok and read is not None:
                frame = read
        if frame is None:
            raise SnapshotUnavailableError(
                f"{node.card} at {port_path} opened but delivered no frame"
            )
        encoded, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not encoded:
            raise SnapshotUnavailableError(
                f"{node.card} at {port_path} produced an unencodable frame"
            )
        return bytes(buffer)
    finally:
        capture.release()


__all__ = ["JPEG_QUALITY", "SNAPSHOT_WARMUP_FRAMES", "SnapshotUnavailableError", "grab_jpeg"]
