"""Turn a blocked matrix cell into a hard stop, and build the async fallback plan.

`10` FR-TRN-064 is `[확정]` M: an over-ceiling combination is a BLOCK, not a
warning. `enforce` is the half of the matrix that makes that real — given a cell,
it raises `PolicyCompatBlockedError` when the cell is blocked, so a caller cannot read
the verdict and proceed anyway. A warning-only matrix would let a 48-dim dataset
reach a 32-dim policy and fail deep in training; this raises at the gate.

When the capability axis forces async chunking (FR-INF-034: sync above the onboard
ceiling is blocked), the fallback is LeRobot's async client, whose `RobotClientConfig`
requires `actions_per_chunk` with no default and defaults `chunk_size_threshold` to
0.5 (`16` D-11; the documented `50 / 0.7` pair is stale). `build_async_chunking_plan`
mirrors that exactly: it rejects a plan that omits `actions_per_chunk`, and it takes
the threshold default from introspection rather than restating a literal.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.policy_matrix.caps import (
    actions_per_chunk_is_required,
    async_chunk_size_threshold_default,
)
from backend.policy_matrix.matrix import Block, MatrixCell


class PolicyCompatBlockedError(Exception):
    """Raised when a blocked matrix cell is enforced.

    Attributes:
        cell: The blocked cell whose enforcement raised.
    """

    def __init__(self, cell: MatrixCell) -> None:
        """Build the exception from the blocked cell.

        Args:
            cell: The cell being enforced; must be blocked.
        """
        self.cell = cell
        reasons = "; ".join(f"[{block.axis}:{block.code}] {block.human}" for block in cell.blocks)
        super().__init__(
            f"policy {cell.policy!r} blocked for state_dim={cell.dataset.state_dim()} on "
            f"target {cell.deploy.target_id!r}: {reasons}"
        )


def enforce(cell: MatrixCell) -> MatrixCell:
    """Return the cell when it is allowed, or raise when it is blocked.

    Args:
        cell: The evaluated cell.

    Returns:
        (MatrixCell) The same cell, when allowed.

    Raises:
        PolicyCompatBlockedError: When the cell carries any block — the FR-TRN-064
            hard stop, never a warning the caller may ignore.
    """
    if cell.blocks:
        raise PolicyCompatBlockedError(cell)
    return cell


def first_block(cell: MatrixCell) -> Block | None:
    """Return the first block on a cell, or None when it is allowed.

    Args:
        cell: The evaluated cell.

    Returns:
        (Block | None) The leading block, or None.
    """
    return cell.blocks[0] if cell.blocks else None


@dataclass(frozen=True)
class AsyncChunkingPlan:
    """The async-inference fallback forced when sync is blocked (`16` D-11).

    Attributes:
        actions_per_chunk: The required chunk width; the request must supply it.
        chunk_size_threshold: The refill threshold, defaulted from introspection.
    """

    actions_per_chunk: int
    chunk_size_threshold: float


def build_async_chunking_plan(
    actions_per_chunk: int | None, chunk_size_threshold: float | None = None
) -> AsyncChunkingPlan:
    """Build the async chunking plan, rejecting an unset `actions_per_chunk`.

    Args:
        actions_per_chunk: The chunk width. There is no default — the installed
            `RobotClientConfig` declares none, and this mirrors that: `None` is
            rejected rather than silently filled.
        chunk_size_threshold: The refill threshold; when None, the introspected
            default (0.5) is used, never the stale `0.7`.

    Returns:
        (AsyncChunkingPlan) The plan.

    Raises:
        ValueError: When `actions_per_chunk` is None while the upstream config
            declares it required — a plan that omits it must not be instantiated.
    """
    if actions_per_chunk is None:
        detail = (
            "" if actions_per_chunk_is_required() else " (note: upstream now declares a default)"
        )
        raise ValueError(
            "actions_per_chunk is required and has no default; supply it explicitly" + detail
        )
    threshold = (
        async_chunk_size_threshold_default()
        if chunk_size_threshold is None
        else chunk_size_threshold
    )
    return AsyncChunkingPlan(actions_per_chunk=actions_per_chunk, chunk_size_threshold=threshold)
