"""The channel axis and one tick's telemetry sample.

`02b` §3 WP-2C-09 fixes the eight channels the dump must carry per joint:
`{q, q̇, τ_meas, τ_model, r, ERR, T_MOS, T_Rotor}` (`12` FR-SAF-065). These are the
physical-telemetry channels the audit record (WP-2A-05) deliberately does not hold —
`backend.audit.record` names them as this package's concern — so they are defined
here, once, with their units beside them.

A sample is a plain float matrix rather than a matrix of unit-tagged values. The
unit safety of `contracts.units` guards conversion *boundaries*; a passive recorder
of already-computed values crosses no boundary, and one tag object per cell for
eight joints times eight channels every tick would cost far more than it protects.
The unit each column carries is therefore documented on the channel, and the values
are read back in the same unit they were recorded in.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from backend.event_ring.constants import EVENT_JOINT_COUNT
from backend.event_ring.errors import EventRingShapeError


class EventChannel(Enum):
    """One recorded channel of the WP-2C-09 dump.

    Each member is a distinct identity (`auto()`), never its unit — several channels
    share a unit (three are Nm, two are degC), and enum members that shared a value
    would silently collapse into aliases, shrinking the eight-channel axis. The unit
    is carried in `_CHANNEL_UNITS` and read through `unit`. Member order is the column
    order of a `TelemetrySample`; `CHANNEL_ORDER` and `CHANNEL_COUNT` derive from it,
    so the channel axis is declared in exactly one place.

    `ERR` is the Damiao feedback ERR nibble (a 0..15 fault code) stored as its integer
    value in a float cell; it is the one dimensionless column.
    """

    Q = auto()
    QDOT = auto()
    TAU_MEAS = auto()
    TAU_MODEL = auto()
    R = auto()
    ERR = auto()
    T_MOS = auto()
    T_ROTOR = auto()

    @property
    def unit(self) -> str:
        """The physical unit of this channel's column."""
        return _CHANNEL_UNITS[self]

    @property
    def column(self) -> int:
        """The channel's fixed column index within a sample's per-joint row."""
        return CHANNEL_ORDER.index(self)


CHANNEL_ORDER: tuple[EventChannel, ...] = tuple(EventChannel)

# The physical unit of each channel's column (`12` FR-SAF-065). `code` marks the ERR
# nibble, the one dimensionless column; the rest are the units the values are
# recorded in and read back in.
_CHANNEL_UNITS: dict[EventChannel, str] = {
    EventChannel.Q: "rad",
    EventChannel.QDOT: "rad/s",
    EventChannel.TAU_MEAS: "Nm",
    EventChannel.TAU_MODEL: "Nm",
    EventChannel.R: "Nm",
    EventChannel.ERR: "code",
    EventChannel.T_MOS: "degC",
    EventChannel.T_ROTOR: "degC",
}

# The channel axis width — the "eight channels" of the WP-2C-09 dump.
CHANNEL_COUNT = len(CHANNEL_ORDER)


@dataclass(frozen=True)
class TelemetrySample:
    """One tick of the eight-joint, eight-channel telemetry the ring retains.

    Attributes:
        at: Monotonic clock reading for this tick, seconds — the retention and
            pre/post windowing axis. Samples are recorded in non-decreasing `at`
            order; the ring's pre-window snapshot relies on that ordering.
        rows: One row of `CHANNEL_COUNT` values per joint, `EVENT_JOINT_COUNT`
            rows, each column in the unit its `EventChannel` declares.
    """

    at: float
    rows: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        """Reject a sample that is not exactly the declared joint-by-channel matrix."""
        if len(self.rows) != EVENT_JOINT_COUNT:
            raise EventRingShapeError(
                f"expected {EVENT_JOINT_COUNT} joint rows, got {len(self.rows)}"
            )
        for index, row in enumerate(self.rows):
            if len(row) != CHANNEL_COUNT:
                raise EventRingShapeError(
                    f"joint {index}: expected {CHANNEL_COUNT} channels, got {len(row)}"
                )

    def joint(self, joint_index: int) -> tuple[float, ...]:
        """Return one joint's row of channel values, in `CHANNEL_ORDER`.

        Args:
            joint_index: Zero-based motor index, gripper last.

        Returns:
            (tuple[float, ...]) The joint's `CHANNEL_COUNT` values.
        """
        return self.rows[joint_index]

    def channel(self, channel: EventChannel) -> tuple[float, ...]:
        """Return one channel's column across all joints.

        Args:
            channel: The channel to slice out.

        Returns:
            (tuple[float, ...]) The channel's value for each joint, joint order.
        """
        column = channel.column
        return tuple(row[column] for row in self.rows)
