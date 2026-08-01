"""WP-2A-06 — the stop path's declared shape and its no-torque-cut static check.

Everything this package holds is checkable without a clock. The stop-path latency is not
measured here and not measured anywhere in this tree: `03` §5.7.0 admits exactly two
sources for the release instant and this rig can supply neither, so the number is out of
scope rather than approximated (`constants.NO_LATENCY_REASON`). PG-STOP-001 is WP-1-05's
gate (`03` §5.7 WP binding) and this package is not one of its consumers.

What this package does carry:

- the absence of `disable_torque` on the stop path, run as a publish-gating refusal over
  the WP-0A-01 scan (`backend.actuation.find_disable_torque`) rather than a second
  scanner. A stop that cuts torque drops a brakeless arm (`04` NFR-MAN-002), and that is
  true at any latency;
- the four-stage path shape — harness-event, transmit, scheduler, CAN — with each stage
  anchored to the symbol that owns its opening event, so a rename in the deadman or the
  actuation spine breaks this declaration instead of leaving it quietly describing code
  that no longer exists.

Public surface:

- `path` — the four stages, their anchors, and the anchor refusal.
- `precondition` — the reused `disable_torque` scan as a refusal.
- `bench` — the artifact assembly with both refusals.
"""

from __future__ import annotations

from backend.stopbench.bench import build_stop_path_artifact
from backend.stopbench.constants import NO_LATENCY_REASON, WP_ID
from backend.stopbench.path import (
    SEGMENT_ORDER,
    STOP_PATH,
    STOP_PATH_END,
    StopPathAnchorMissingError,
    StopPathSegment,
    StopPathStage,
    assert_anchors_resolve,
    path_record,
)
from backend.stopbench.precondition import (
    DEFAULT_STOP_PATH_ROOT,
    STOP_PATH_TREE,
    DisableTorqueOnStopPathError,
    NoDisableTorqueCheck,
    StopPathScanEmptyError,
    assert_no_disable_torque,
    check_no_disable_torque,
)

__all__ = [
    "DEFAULT_STOP_PATH_ROOT",
    "NO_LATENCY_REASON",
    "SEGMENT_ORDER",
    "STOP_PATH",
    "STOP_PATH_END",
    "STOP_PATH_TREE",
    "WP_ID",
    "DisableTorqueOnStopPathError",
    "NoDisableTorqueCheck",
    "StopPathAnchorMissingError",
    "StopPathScanEmptyError",
    "StopPathSegment",
    "StopPathStage",
    "assert_anchors_resolve",
    "assert_no_disable_torque",
    "build_stop_path_artifact",
    "check_no_disable_torque",
    "path_record",
]
