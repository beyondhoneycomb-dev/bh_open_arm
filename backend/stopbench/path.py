"""The stop path's declared shape: four stages, each anchored to the code that owns it.

`02b` WP-2A-06 names four stages between the deadman lease expiry and the Cat-2 hold
frame on the bus — harness-event, transmit, scheduler, CAN. That ordering is a property
of the architecture, not of any measurement: it says the stop path crosses exactly these
four hand-offs, in this order, and it stays true whether or not anyone can time them.

No stage carries a duration and none is measured here. Timing the path needs the release
instant and the CAN frame on one trusted clock domain (`03` §5.7.0), which this rig cannot
supply (`backend.stopbench.constants.NO_LATENCY_REASON`), so this module publishes the
shape and nothing else.

What keeps the shape from rotting into a comment is the anchor: each stage names the
`module:Symbol` that owns the event opening it, and the declaration refuses to publish
when an anchor no longer resolves. A stage boundary whose owning symbol was renamed or
deleted is a stop path that has silently changed shape, and that is the failure this
module exists to catch.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from enum import Enum
from typing import Any

# The terminal event of the path. It has no code anchor because it is a bus event, not a
# call: the first byte of the hold frame is observable only on the wire.
STOP_PATH_END = "first byte of the Cat-2 MIT hold frame on the CAN bus"


class StopPathSegment(Enum):
    """The four stages the stop path is decomposed into (`02b` WP-2A-06).

    Ordered as they occur: the deadman release surfaces as a harness event, is carried
    into the control process, is turned into a hold frame by one scheduler tick, and is
    written to the CAN bus. A change to the stop path lands in exactly one of these,
    which is why the split is worth declaring.
    """

    HARNESS_EVENT = "harness_event"
    TRANSMIT = "transmit"
    SCHEDULER = "scheduler"
    CAN = "can"


class StopPathAnchorMissingError(Exception):
    """A declared stage boundary names a symbol that no longer exists.

    Raised instead of publishing the shape: a stage anchored to a symbol that cannot be
    imported means the declaration and the code have diverged, and a stop-path shape that
    describes code nobody runs is worse than no shape at all.
    """


@dataclass(frozen=True)
class StopPathStage:
    """One stage of the stop path and the code owning the event that opens it.

    Attributes:
        segment: Which of the four stages this is.
        opens_at: The event that opens the stage, in the terms the plan uses.
        anchor: `module:Symbol` owning that event. Resolved, never merely quoted, so a
            rename in the owning package breaks this declaration instead of outliving it.
        owner_wp: The work package that owns the anchored symbol, recorded so a reader
            knows whose code to open.
    """

    segment: StopPathSegment
    opens_at: str
    anchor: str
    owner_wp: str

    def resolve(self) -> object:
        """Import the anchored symbol.

        Returns:
            (object) The anchored symbol.

        Raises:
            StopPathAnchorMissingError: If the module or the symbol is absent.
        """
        module_name, _, symbol_name = self.anchor.partition(":")
        try:
            module = importlib.import_module(module_name)
        except ImportError as absent:
            raise StopPathAnchorMissingError(
                f"stop-path stage {self.segment.value} anchors {self.anchor}, whose module "
                f"cannot be imported: {absent}"
            ) from absent
        try:
            return getattr(module, symbol_name)
        except AttributeError as absent:
            raise StopPathAnchorMissingError(
                f"stop-path stage {self.segment.value} anchors {self.anchor}, and "
                f"{module_name} has no {symbol_name}"
            ) from absent

    def as_record(self) -> dict[str, str]:
        """Serialize the stage for the evidence artifact.

        Returns:
            (dict[str, str]) The stage name, its opening event, its anchor, and the
            package owning the anchored symbol.
        """
        return {
            "segment": self.segment.value,
            "opens_at": self.opens_at,
            "anchor": self.anchor,
            "owner_wp": self.owner_wp,
        }


# The stop path as declared, in the order the stages occur. The anchors cross three
# packages on purpose: the release is the deadman lease's (WP-2A-02), the hold decision is
# the Wave-1 spine's, and the write is the single CAN writer's — which is the same
# crossing `02b` WP-2A-06 names as harness-event / transmit / scheduler / CAN.
STOP_PATH: tuple[StopPathStage, ...] = (
    StopPathStage(
        segment=StopPathSegment.HARNESS_EVENT,
        opens_at="the deadman lease lapses on the server monotonic clock",
        anchor="backend.deadman:DeadmanLease",
        owner_wp="WP-2A-02",
    ),
    StopPathStage(
        segment=StopPathSegment.TRANSMIT,
        opens_at="the lapse crosses into the control process as a latch signal",
        anchor="backend.deadman:DeadmanMonitor",
        owner_wp="WP-2A-02",
    ),
    StopPathStage(
        segment=StopPathSegment.SCHEDULER,
        opens_at="the scheduler tick that turns the lapse into a Cat-2 hold frame",
        anchor="backend.actuation:ActuationScheduler",
        owner_wp="WP-1-03",
    ),
    StopPathStage(
        segment=StopPathSegment.CAN,
        opens_at="the batched MIT write that puts the hold frame on the bus",
        anchor="backend.actuation:CanWriter",
        owner_wp="WP-1-03",
    ),
)

SEGMENT_ORDER: tuple[StopPathSegment, ...] = tuple(stage.segment for stage in STOP_PATH)


def assert_anchors_resolve(
    path: tuple[StopPathStage, ...] = STOP_PATH,
) -> tuple[StopPathStage, ...]:
    """Refuse to publish the shape unless every stage anchor still resolves.

    Args:
        path: The declared stages to check.

    Returns:
        (tuple[StopPathStage, ...]) The checked path, for the caller to record.

    Raises:
        StopPathAnchorMissingError: If any anchor's module or symbol is absent.
    """
    for stage in path:
        stage.resolve()
    return path


def path_record(path: tuple[StopPathStage, ...] = STOP_PATH) -> dict[str, Any]:
    """Serialize the declared stop-path shape for the evidence artifact.

    Args:
        path: The declared stages to serialize.

    Returns:
        (dict[str, Any]) The ordered stages, the terminal bus event, and the statement
        that the shape carries no durations.
    """
    return {
        "stage_count": len(path),
        "stages": [stage.as_record() for stage in path],
        "ends_at": STOP_PATH_END,
        "durations": None,
    }
