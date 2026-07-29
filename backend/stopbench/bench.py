"""Assemble the WP-2A-06 stop-path evidence, refusing every un-trustworthy input.

Two things come together here, and each reuses a single-source rule rather than restating
it:

  * The stop path must hold no `disable_torque` — run before anything else, delegated to
    the reused `backend.actuation` scan (`backend.stopbench.precondition`). On a brakeless
    arm a stop that drops torque is a fall, so this is refused, not reported.
  * The four-stage path shape is published only while every stage anchor still resolves
    (`backend.stopbench.path`).

No latency, no percentile, no verdict against a target: the stop-path timing is not
measured in this tree, and the artifact says so in its own `no_latency_reason` field
rather than leaving a reader to infer it from an absence.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.stopbench.constants import NO_LATENCY_REASON, WP_ID
from backend.stopbench.path import STOP_PATH, assert_anchors_resolve, path_record
from backend.stopbench.precondition import (
    DEFAULT_STOP_PATH_ROOT,
    assert_no_disable_torque,
)


def build_stop_path_artifact(
    *,
    stop_path_root: Path = DEFAULT_STOP_PATH_ROOT,
    exclude: Iterable[Path] = (),
) -> dict[str, Any]:
    """Assemble the WP-2A-06 evidence, refusing it when a precondition fails.

    Args:
        stop_path_root: The stop-path tree scanned for `disable_torque`.
        exclude: Directories to skip in the `disable_torque` scan.

    Returns:
        (dict[str, Any]) The evidence: the `disable_torque` precondition result, the
        declared four-stage path shape, and the reason no latency accompanies them.

    Raises:
        StopPathScanEmptyError: If the `disable_torque` scan parsed no file.
        DisableTorqueOnStopPathError: If the stop path holds `disable_torque`.
        StopPathAnchorMissingError: If a declared stage anchor no longer resolves.
    """
    precondition = assert_no_disable_torque(stop_path_root, exclude=exclude)
    path = assert_anchors_resolve(STOP_PATH)

    return {
        "wp_id": WP_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "no_disable_torque_precondition": precondition.as_record(),
        "path_shape": path_record(path),
        "no_latency_reason": NO_LATENCY_REASON,
    }
