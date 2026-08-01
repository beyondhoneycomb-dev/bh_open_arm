"""WP-2C-06 — the reaction path's declared shape and its no-torque-cut static check.

Everything this package holds is checkable without a clock. The reaction time is not
measured here and not measured anywhere in this tree: `03` §5.7.0 admits exactly two
sources for correlating a software event to a bus frame and this rig can supply neither,
so the number is out of scope rather than approximated
(`constants.NO_LATENCY_REASON`).

What this package does carry:

- the absence of `disable_torque` on the reaction path, run as a publish-gating refusal
  over the WP-0A-01 scan (`backend.actuation.find_disable_torque`) rather than a second
  scanner. The reaction is a continuous STOP_HOLD MIT send, never a torque cut
  (`02b` WP-2C-05), and that is true at any latency;
- the three-stage path shape — select, schedule, CAN — with each stage anchored to the
  symbol that owns its opening event. All three anchors resolve inside one interpreter,
  which is the checkable form of the same-process claim (`02b` WP-2C-10) the path's shape
  rests on.

Public surface:

- `path` — the three stages, their anchors, and the anchor refusal.
- `precondition` — the reused `disable_torque` scan as a refusal.
- `bench` — the artifact assembly with both refusals.
"""

from __future__ import annotations

from backend.reaction_bench.bench import build_reaction_path_artifact
from backend.reaction_bench.constants import NO_LATENCY_REASON, WP_ID
from backend.reaction_bench.path import (
    REACTION_PATH,
    REACTION_PATH_END,
    SEGMENT_ORDER,
    ReactionPathAnchorMissingError,
    ReactionPathStage,
    ReactionSegment,
    assert_anchors_resolve,
    path_record,
)
from backend.reaction_bench.precondition import (
    DEFAULT_REACTION_PATH_ROOT,
    REACTION_PATH_TREE,
    DisableTorqueOnReactionPathError,
    NoDisableTorqueCheck,
    ReactionPathScanEmptyError,
    assert_no_disable_torque,
    check_no_disable_torque,
)

__all__ = [
    "DEFAULT_REACTION_PATH_ROOT",
    "NO_LATENCY_REASON",
    "REACTION_PATH",
    "REACTION_PATH_END",
    "REACTION_PATH_TREE",
    "SEGMENT_ORDER",
    "WP_ID",
    "DisableTorqueOnReactionPathError",
    "NoDisableTorqueCheck",
    "ReactionPathAnchorMissingError",
    "ReactionPathScanEmptyError",
    "ReactionPathStage",
    "ReactionSegment",
    "assert_anchors_resolve",
    "assert_no_disable_torque",
    "build_reaction_path_artifact",
    "check_no_disable_torque",
    "path_record",
]
