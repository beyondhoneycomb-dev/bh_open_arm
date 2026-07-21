"""The four-parameter synthetic load profile — the thing every artifact must carry.

`03` §5.1a fixes the contract: a synthetic GIL load is an *approximation* of the
canonical condition-4 load, not an upper bound on it, and the only thing that makes
an approximation comparable to the real measurement (`PG-RT-001b`, `WP-3C-02`) is a
verbatim record of the load shape it was produced under. So the shape is pinned to
exactly four parameters — `{stream count, resolution, PNG write bytes/frame,
serialize bytes/tick}` — and `02a` WP-0C-06 acceptance ② refuses to publish any
artifact that does not record all four.

`resolution` counts as one parameter carried as a `(width, height)` pair. The class
is frozen: a profile is an immutable fact stamped onto a result, never mutated after
a run begins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The canonical parameter names, in the order `03` §5.1a lists them. The artifact
# builder checks a run's recorded profile against exactly this set (acceptance ②):
# a run missing any one of these is refused, because a profile that cannot be
# compared against `b` has zero value as an early signal (03 §5.1a).
REQUIRED_PARAM_KEYS: tuple[str, ...] = (
    "stream_count",
    "resolution",
    "png_write_bytes_per_frame",
    "serialize_bytes_per_tick",
)


class InvalidLoadProfileError(ValueError):
    """A load profile whose parameters are absent or negative.

    A negative byte count or a negative stream count cannot describe a real load, so
    it is rejected at construction rather than silently producing a degenerate run
    whose artifact would still claim to be recorded.
    """


@dataclass(frozen=True)
class LoadProfile:
    """The four-parameter shape of one synthetic GIL load.

    Attributes:
        stream_count: How many synthetic camera streams are grabbed per load tick.
        resolution_width: Width, in pixels, of each synthetic frame.
        resolution_height: Height, in pixels, of each synthetic frame.
        png_write_bytes_per_frame: Bytes the lossless-PNG stage writes per frame.
        serialize_bytes_per_tick: Bytes the WS-serialization stage emits per tick.
    """

    stream_count: int
    resolution_width: int
    resolution_height: int
    png_write_bytes_per_frame: int
    serialize_bytes_per_tick: int

    def __post_init__(self) -> None:
        """Reject any negative parameter — a load shape must be physically sayable."""
        negative = [
            name
            for name in (
                "stream_count",
                "resolution_width",
                "resolution_height",
                "png_write_bytes_per_frame",
                "serialize_bytes_per_tick",
            )
            if getattr(self, name) < 0
        ]
        if negative:
            raise InvalidLoadProfileError(f"load profile has negative parameter(s): {negative}")

    @property
    def resolution(self) -> tuple[int, int]:
        """The frame resolution as a `(width, height)` pair — one of the four params."""
        return (self.resolution_width, self.resolution_height)

    @property
    def is_no_load(self) -> bool:
        """Whether this profile exerts no load at all.

        A profile with no streams and no bytes on either the PNG or the
        serialization stage generates no work. Acceptance ③ turns on this case: a
        no-load harness must NOT produce a cycle-time distribution distinguishable
        from idle, which is what proves the loaded case's separation is the load
        biting and not the instrument lying.
        """
        return self.stream_count == 0 or (
            self.png_write_bytes_per_frame == 0 and self.serialize_bytes_per_tick == 0
        )

    def as_record(self) -> dict[str, Any]:
        """Render the profile as the four canonical parameters for the artifact.

        Returns:
            (dict[str, Any]) A mapping keyed by `REQUIRED_PARAM_KEYS`. The artifact
            builder embeds this verbatim; `b` reads it to quantify how well the
            synthetic shape approximated the real load (03 §5.1a, WP-0C-06 ⑥).
        """
        return {
            "stream_count": self.stream_count,
            "resolution": [self.resolution_width, self.resolution_height],
            "png_write_bytes_per_frame": self.png_write_bytes_per_frame,
            "serialize_bytes_per_tick": self.serialize_bytes_per_tick,
        }


def profile_is_fully_recorded(record: dict[str, Any] | None) -> bool:
    """Report whether a profile record carries all four parameters with real values.

    Args:
        record: A candidate profile record, or None when a run recorded none.

    Returns:
        (bool) True only when every one of `REQUIRED_PARAM_KEYS` is present and not
        None. This is the predicate acceptance ② enforces before publishing.
    """
    if not record:
        return False
    return all(record.get(key) is not None for key in REQUIRED_PARAM_KEYS)
