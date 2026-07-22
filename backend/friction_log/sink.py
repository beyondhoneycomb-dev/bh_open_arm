"""The log sink — where frames go after the tap emits them.

`LogSink` is the seam between the tap (which must never transmit) and storage. Its one
method is `emit`, deliberately not named for any socket or bus operation, so the
no-transmit static scan has no transmit symbol to find on this path. `MemoryLogSink`
keeps every frame for the frequency/jitter analysis and the acceptance assertions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from backend.friction_log.frame import LogFrame


class LogSink(Protocol):
    """A destination for log frames, written once per tick."""

    def emit(self, frame: LogFrame) -> None:
        """Accept one tick's frame.

        Args:
            frame: The frame to store or fold in.
        """
        ...


@dataclass
class MemoryLogSink:
    """A sink that keeps every frame in order, for analysis and assertions."""

    frames: list[LogFrame] = field(default_factory=list)

    def emit(self, frame: LogFrame) -> None:
        """Append a frame.

        Args:
            frame: The frame to keep.
        """
        self.frames.append(frame)

    def count(self) -> int:
        """Return the number of frames captured.

        Returns:
            (int) Frame count — equal to the tick count for pattern A.
        """
        return len(self.frames)
