"""WP-3B-06 structural guarantees: one WS out, read-latest in, no second stream.

`02b` §6.2 acceptance ④ ("별도 WebRTC/RTSP/Foxglove 스트림 0개") and the
`FAIL_BLOCKING` boundary ("프리뷰가 캡처를 블로킹"). These are proved by the shape of
the code, not by runtime behaviour: the package opens none of the parallel
realtime stacks `CTR-WS@v1` forbids, its camera surface can only be read latest-wins
and non-blocking, and its egress surface can only send binary — never drive the robot.
"""

from __future__ import annotations

from pathlib import Path

import backend.sensing.preview as preview
from backend.sensing.preview.sink import PreviewSink
from backend.sensing.preview.source import LatestFrameSource
from contracts.ws import FORBIDDEN_PARALLEL_STACKS


def _package_sources() -> str:
    root = Path(preview.__file__).parent
    return "\n".join(path.read_text(encoding="utf-8").lower() for path in sorted(root.glob("*.py")))


def test_package_opens_no_forbidden_parallel_realtime_stack() -> None:
    """No source in the package names a forbidden parallel realtime stack (④)."""
    sources = _package_sources()
    for stack in FORBIDDEN_PARALLEL_STACKS:
        assert stack not in sources, f"preview package must not open a {stack!r} stream"


def test_source_surface_is_read_only_and_non_blocking() -> None:
    """`LatestFrameSource` offers only `read_latest` — no blocking or capture-control read."""
    members = {name for name in dir(LatestFrameSource) if not name.startswith("_")}
    assert "read_latest" in members
    for blocking in ("read", "async_read", "grab", "capture"):
        assert blocking not in members


def test_sink_surface_is_tx_only_and_cannot_drive_the_robot() -> None:
    """`PreviewSink` offers only a buffer probe and a binary send — no command path."""
    members = {name for name in dir(PreviewSink) if not name.startswith("_")}
    assert "send_binary" in members
    assert "buffered_amount" in members
    for command in ("send_action", "send_command", "write", "recv", "receive"):
        assert command not in members
