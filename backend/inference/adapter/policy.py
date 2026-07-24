"""The policy surface the engine drives, and the action -> mailbox-target conversion.

The engine does not care whether the policy is ACT, pi0, or a fixture — it drives a
small `ChunkPolicy` surface whose method names match LeRobot's (`reset`,
`select_action`, `predict_action_chunk`), so a real `PreTrainedPolicy` satisfies it
and the offline gates can supply a deterministic stand-in. What the engine *does*
enforce is the boundary: a policy emits a 16-wide position vector, and this module
turns it into a `RequestedPositionAction` — the pre-clamp, position-only CTR-ACT
target the producer publishes to the mailbox. It never becomes an MIT frame here;
the scheduler is the sole writer.

Relative-action detection lives here too (`FR-INF-015`, CG-4A-07d). A relative-action
policy is one whose preprocessor carries an enabled `RelativeActionsProcessorStep`,
exactly the test `rollout/inference/rtc.py` makes; `relative_action_from_preprocessor`
imports that step lazily so this module stays torch-free for callers that already
know the answer via `PolicyProfile`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from backend.inference.adapter.params import PolicyProfile
from contracts.action import BIMANUAL_ACTION_DIM, RequestedPositionAction
from contracts.units import Deg


@runtime_checkable
class ChunkPolicy(Protocol):
    """The minimal policy surface the inference engine drives.

    Method names match LeRobot's `PreTrainedPolicy` so a real policy is a drop-in:
    `select_action` for the sync path (one action per call) and `predict_action_chunk`
    for the RTC path (a chunk of actions). `reset` clears episode-scoped internal
    state (`FR-INF-066`).
    """

    def reset(self) -> None:
        """Clear episode-scoped internal state (hidden state, action buffers)."""
        ...

    def select_action(self, observation: Any) -> Sequence[float]:
        """Return one 16-wide position action for the given observation (sync path).

        Args:
            observation: The observation frame.

        Returns:
            (Sequence[float]) A `BIMANUAL_ACTION_DIM`-wide position vector, degrees.
        """
        ...

    def predict_action_chunk(self, observation: Any) -> Sequence[Sequence[float]]:
        """Return a chunk of 16-wide position actions (RTC path).

        Args:
            observation: The observation frame.

        Returns:
            (Sequence[Sequence[float]]) Ordered position vectors, each 16-wide.
        """
        ...

    @property
    def profile(self) -> PolicyProfile:
        """The static profile the factory reads to gate a backend selection."""
        ...


def action_vector_to_request(vector: Sequence[float]) -> RequestedPositionAction:
    """Convert a policy's 16-wide position vector to a mailbox `RequestedPositionAction`.

    The result is the pre-clamp, position-only CTR-ACT request; the scheduler clamps
    it to an accepted target before it ever becomes a CAN frame. This function never
    touches torque or a CAN handle.

    Args:
        vector: The policy output, `BIMANUAL_ACTION_DIM` position values in degrees.

    Returns:
        (RequestedPositionAction) The 16-dim position request to publish.

    Raises:
        ValueError: If `vector` is not `BIMANUAL_ACTION_DIM` wide (surfaced here
            rather than as an opaque failure deep in the mailbox).
    """
    values = tuple(float(component) for component in vector)
    if len(values) != BIMANUAL_ACTION_DIM:
        raise ValueError(
            f"policy action must be {BIMANUAL_ACTION_DIM}-wide (position-only); got {len(values)}"
        )
    return RequestedPositionAction(values=tuple(Deg(component) for component in values))


def relative_action_from_preprocessor(preprocessor: Any) -> bool:
    """Report whether a LeRobot preprocessor makes the policy relative-action.

    Mirrors `rollout/inference/rtc.py`'s own test — an enabled
    `RelativeActionsProcessorStep` among the preprocessor steps — importing that step
    lazily so this module does not pull the torch-bearing processor stack for callers
    that already carry the answer on `PolicyProfile`.

    Args:
        preprocessor: A LeRobot `PolicyProcessorPipeline` with a `steps` iterable.

    Returns:
        (bool) True when a relative-action step is present and enabled.
    """
    from lerobot.processor.relative_action_processor import RelativeActionsProcessorStep

    steps = getattr(preprocessor, "steps", ())
    return any(
        isinstance(step, RelativeActionsProcessorStep) and getattr(step, "enabled", False)
        for step in steps
    )
