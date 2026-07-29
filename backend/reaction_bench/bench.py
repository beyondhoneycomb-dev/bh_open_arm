"""Assemble the WP-2C-06 reaction-path evidence, refusing every un-trustworthy input.

Two things come together here, and each reuses a single-source rule rather than restating
it:

  * The reaction path must hold no `disable_torque` — run before anything else, delegated
    to the reused `backend.actuation` scan (`backend.reaction_bench.precondition`). The
    reaction is a continuous STOP_HOLD MIT send, and on a brakeless arm a reaction that
    drops torque is a fall, so this is refused, not reported.
  * The three-stage path shape is published only while every stage anchor still resolves
    (`backend.reaction_bench.path`).

No latency, no histogram, no verdict against a target: the reaction time is not measured
in this tree, and the artifact says so in its own `no_latency_reason` field rather than
leaving a reader to infer it from an absence.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.reaction_bench.constants import NO_LATENCY_REASON, WP_ID
from backend.reaction_bench.path import REACTION_PATH, assert_anchors_resolve, path_record
from backend.reaction_bench.precondition import (
    DEFAULT_REACTION_PATH_ROOT,
    assert_no_disable_torque,
)


def build_reaction_path_artifact(
    *,
    reaction_path_root: Path = DEFAULT_REACTION_PATH_ROOT,
    exclude: Iterable[Path] = (),
) -> dict[str, Any]:
    """Assemble the WP-2C-06 evidence, refusing it when a precondition fails.

    Args:
        reaction_path_root: The reaction-path tree scanned for `disable_torque`.
        exclude: Directories to skip in the `disable_torque` scan.

    Returns:
        (dict[str, Any]) The evidence: the `disable_torque` precondition result, the
        declared three-stage path shape, and the reason no latency accompanies them.

    Raises:
        ReactionPathScanEmptyError: If the `disable_torque` scan parsed no file.
        DisableTorqueOnReactionPathError: If the reaction path holds `disable_torque`.
        ReactionPathAnchorMissingError: If a declared stage anchor no longer resolves.
    """
    precondition = assert_no_disable_torque(reaction_path_root, exclude=exclude)
    path = assert_anchors_resolve(REACTION_PATH)

    return {
        "wp_id": WP_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "no_disable_torque_precondition": precondition.as_record(),
        "path_shape": path_record(path),
        "no_latency_reason": NO_LATENCY_REASON,
    }
