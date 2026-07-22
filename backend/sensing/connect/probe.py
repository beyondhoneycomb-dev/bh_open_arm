"""The liveness boundary a tolerant connect probes each camera through.

`06` §2.12 opens every camera *independently* and treats one that yields no frame as
dead — warned and skipped, never a reason to fail the arm. To decide "did a live
frame arrive" without depending on a real camera, the connect talks to any object
that can hand back the freshest frame at or before an index, or `None` when there is
none. That is exactly the frozen synthetic fixture's `read_latest(up_to_index)`
(`contracts/fixtures/synthetic_camera.py`), so the fixture *is* a valid probe and no
real hardware is faked here; a real camera backend satisfies the same shape.

Ownership: a probe is a read-only view onto a camera's frame stream. The connect
calls it once at open time and never stores it; a raised exception or a `None` is a
dead camera, not a crash to propagate (that tolerance is the whole contract).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class LiveFrameSource(Protocol):
    """Anything that can non-blockingly return its freshest frame, or nothing.

    A non-`None` return means a live frame was available at or before `up_to_index`;
    `None` means every index up to it was dropped — the camera is dead for now. The
    return is deliberately untyped past "some frame object": the connect only reads
    liveness, never the pixel bytes, so a synthetic frame, a real frame and a
    recorded stand-in are all valid without a shared frame class.
    """

    def read_latest(self, up_to_index: int) -> object | None:
        """Return the freshest live frame at or before an index, or None."""
        ...


@dataclass(frozen=True)
class RecordedFrame:
    """A stand-in for 'a live frame arrived', carrying only the slot it belonged to.

    The deferred real-fixture re-verification (`deferred.py`) records *that* a frame
    arrived per slot, not its bytes, so this is what a recorded-live camera hands
    back — enough for the connect's liveness check, honest about carrying no pixels.

    Attributes:
        slot: The slot key whose recorded capture this frame stands for.
    """

    slot: str


@dataclass(frozen=True)
class RecordedLiveness:
    """A `LiveFrameSource` driven by a recorded per-slot liveness fact.

    Lets the deferred hook re-run the identical tolerant connect over real captured
    output: a slot recorded live yields a `RecordedFrame`, one recorded dead yields
    `None`, so the same skip/warn path runs against real bytes without a live camera.

    Attributes:
        slot: The slot key this source stands in for.
        is_live: Whether the real capture recorded a frame arriving for this slot.
    """

    slot: str
    is_live: bool

    def read_latest(self, up_to_index: int) -> object | None:  # noqa: ARG002 — LiveFrameSource shape
        """Return a recorded frame when the slot was live, else None."""
        return RecordedFrame(self.slot) if self.is_live else None
