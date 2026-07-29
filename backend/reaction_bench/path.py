"""The reaction path's declared shape: three stages, each anchored to the code that owns it.

Between detection confirmed (`WP-2C-04`) and the first reaction MIT frame on the bus
(`WP-2C-05`) the reaction path crosses three hand-offs — select, schedule, CAN. The
reaction path is *same-process*: detection and reaction share one control process and the
feedback is a single function call (`02b` WP-2C-10), so unlike the stop path there is no
network transmit hop, and that absence is the shape's most load-bearing claim.

No stage carries a duration and none is measured here. Timing the path needs the confirm
instant and the CAN frame on one trusted clock domain (`03` §5.7.0), which this rig cannot
supply (`backend.reaction_bench.constants.NO_LATENCY_REASON`), so this module publishes
the shape and nothing else.

What keeps the shape from rotting into a comment is the anchor: each stage names the
`module:Symbol` that owns the event opening it, and the declaration refuses to publish
when an anchor no longer resolves. A stage boundary whose owning symbol was renamed or
deleted is a reaction path that has silently changed shape, and that is the failure this
module exists to catch.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from enum import Enum
from typing import Any

# The terminal event of the path. It has no code anchor because it is a bus event, not a
# call: the first byte of the reaction frame is observable only on the wire.
REACTION_PATH_END = "first byte of the first reaction MIT frame on the CAN bus"


class ReactionSegment(Enum):
    """The three consecutive stages the reaction path is decomposed into.

    Ordered as they occur: once detection is confirmed the reaction strategy is selected
    (`WP-2C-05`), the next scheduler tick turns it into a MIT hold frame, and that frame is
    written to the CAN bus.
    """

    SELECT = "select"
    SCHEDULE = "schedule"
    CAN = "can"


class ReactionPathAnchorMissingError(Exception):
    """A declared stage boundary names a symbol that no longer exists.

    Raised instead of publishing the shape: a stage anchored to a symbol that cannot be
    imported means the declaration and the code have diverged, and a reaction-path shape
    that describes code nobody runs is worse than no shape at all.
    """


@dataclass(frozen=True)
class ReactionPathStage:
    """One stage of the reaction path and the code owning the event that opens it.

    Attributes:
        segment: Which of the three stages this is.
        opens_at: The event that opens the stage, in the terms the plan uses.
        anchor: `module:Symbol` owning that event. Resolved, never merely quoted, so a
            rename in the owning package breaks this declaration instead of outliving it.
        owner_wp: The work package that owns the anchored symbol, recorded so a reader
            knows whose code to open.
    """

    segment: ReactionSegment
    opens_at: str
    anchor: str
    owner_wp: str

    def resolve(self) -> object:
        """Import the anchored symbol.

        Returns:
            (object) The anchored symbol.

        Raises:
            ReactionPathAnchorMissingError: If the module or the symbol is absent.
        """
        module_name, _, symbol_name = self.anchor.partition(":")
        try:
            module = importlib.import_module(module_name)
        except ImportError as absent:
            raise ReactionPathAnchorMissingError(
                f"reaction-path stage {self.segment.value} anchors {self.anchor}, whose module "
                f"cannot be imported: {absent}"
            ) from absent
        try:
            return getattr(module, symbol_name)
        except AttributeError as absent:
            raise ReactionPathAnchorMissingError(
                f"reaction-path stage {self.segment.value} anchors {self.anchor}, and "
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


# The reaction path as declared, in the order the stages occur. Every anchor is a
# same-process symbol: that all three resolve inside one interpreter is the checkable form
# of "detection and reaction share one process" (`02b` WP-2C-10).
REACTION_PATH: tuple[ReactionPathStage, ...] = (
    ReactionPathStage(
        segment=ReactionSegment.SELECT,
        opens_at="the confirm gate latches a detection as confirmed",
        anchor="backend.threshold:ConfirmHysteresisGate",
        owner_wp="WP-2C-04",
    ),
    ReactionPathStage(
        segment=ReactionSegment.SCHEDULE,
        opens_at="the reaction policy selects the strategy and latches it",
        anchor="backend.reaction:ReactionPolicy",
        owner_wp="WP-2C-05",
    ),
    ReactionPathStage(
        segment=ReactionSegment.CAN,
        opens_at="the batched MIT write that puts the reaction frame on the bus",
        anchor="backend.actuation:CanWriter",
        owner_wp="WP-1-03",
    ),
)

SEGMENT_ORDER: tuple[ReactionSegment, ...] = tuple(stage.segment for stage in REACTION_PATH)


def assert_anchors_resolve(
    path: tuple[ReactionPathStage, ...] = REACTION_PATH,
) -> tuple[ReactionPathStage, ...]:
    """Refuse to publish the shape unless every stage anchor still resolves.

    Args:
        path: The declared stages to check.

    Returns:
        (tuple[ReactionPathStage, ...]) The checked path, for the caller to record.

    Raises:
        ReactionPathAnchorMissingError: If any anchor's module or symbol is absent.
    """
    for stage in path:
        stage.resolve()
    return path


def path_record(path: tuple[ReactionPathStage, ...] = REACTION_PATH) -> dict[str, Any]:
    """Serialize the declared reaction-path shape for the evidence artifact.

    Args:
        path: The declared stages to serialize.

    Returns:
        (dict[str, Any]) The ordered stages, the terminal bus event, and the statement
        that the shape carries no durations.
    """
    return {
        "stage_count": len(path),
        "stages": [stage.as_record() for stage in path],
        "ends_at": REACTION_PATH_END,
        "durations": None,
    }
