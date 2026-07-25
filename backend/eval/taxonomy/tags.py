"""The failure-tag schema — every tag carries the discriminating signal it is read from.

`02c` §3.4 fixes the load-bearing rule of this WP: the classification axis is not
"what failed" but "which layer failed", and every layer's axis is derived only from a
signal we already hold. So a `FailureTag` is never a bare name — each one carries a
`FailureTagSpec` whose `signal` field records the discriminating signal that pins it.
A tag with no signal is forbidden (CG-4C-04a): a signal-less tag gets attached by
labeler impression, and a classification aggregated over impressions measures the
labeler, not the policy. `FailureTagSpec.__post_init__` refuses an empty signal, so
the "0 signal-less tags" invariant is a construction-time guarantee, not a hope.

Three derivation kinds keep phase-1 (this batch) honest about what is built versus
what is a deferred slot:

- `AUTO` — the nine machine tags the WP-4C-04 correlation engine auto-derives from the
  committed WP-4A-08 signals this batch. Built here.
- `HUMAN` — the three phase-2 tags a human assigns (`POLICY_WRONG_ACTION`,
  `RESET_ERROR`, `AMBIGUOUS`). The schema slot exists; no code fabricates one here.
- `FSM` — `TIMEOUT`, a separate terminal state the WP-4C-01 rollout FSM owns
  (CG-4C-01c). Deferred with the rest of the FSM.

`AMBIGUOUS` is a first-class tag on purpose: real failures will not fit these twelve
axes, and the `AMBIGUOUS` rate is the measure of how far the taxonomy has drifted from
reality (`02c` §3.4 workflow-shape row). That is why it carries a signal too — "the labeler
could not decide" is itself the discriminating signal, not the absence of one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TagAxis(Enum):
    """The layer a failure is attributed to (`02c` §3.4 per-layer axis)."""

    POLICY = "policy"
    INFRA = "infra"
    SAFETY = "safety"
    ENVIRONMENT = "environment"
    JUDGMENT = "judgment"


class TagDerivation(Enum):
    """How a tag is pinned, which fixes what is built here versus deferred.

    AUTO tags are the nine machine tags the correlation engine derives from committed
    signals in this phase-1 batch. HUMAN tags are the phase-2 human-assigned tags —
    the schema carries the slot, no code invents the value. FSM is `TIMEOUT`, owned by
    the WP-4C-01 rollout FSM and deferred with it.
    """

    AUTO = "auto"
    HUMAN = "human"
    FSM = "fsm"


class FailureTag(Enum):
    """One episode-failure attribution. Multiple tags per episode are allowed (CG-4C-04e)."""

    POLICY_WRONG_ACTION = "policy_wrong_action"
    POLICY_OUT_OF_BOUNDS = "policy_out_of_bounds"
    POLICY_RUNAWAY = "policy_runaway"
    POLICY_INVALID_OUTPUT = "policy_invalid_output"
    QUEUE_STARVATION = "queue_starvation"
    REMOTE_DISCONNECT = "remote_disconnect"
    REMOTE_EMPTY_ACTION = "remote_empty_action"
    SAFETY_STOP = "safety_stop"
    COLLISION = "collision"
    TORQUE_LIMIT = "torque_limit"
    RESET_ERROR = "reset_error"
    TIMEOUT = "timeout"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class FailureTagSpec:
    """The definition of one tag: its layer, how it is pinned, and its discriminating signal.

    The `signal` field is mandatory and non-empty — `__post_init__` rejects a blank
    one — because CG-4C-04a forbids a tag pinned by impression alone. The field states
    the one signal that distinguishes this tag from every other; for a HUMAN tag it
    states the signal the labeler judges against, so even a human decision is anchored
    to something we hold, never to a free-floating impression.

    Attributes:
        axis: The layer the failure is attributed to.
        derivation: AUTO (engine-derived here), HUMAN (phase-2 slot), or FSM (WP-4C-01).
        signal: The discriminating signal that pins this tag. Never empty.
    """

    axis: TagAxis
    derivation: TagDerivation
    signal: str

    def __post_init__(self) -> None:
        """Reject a tag defined without a discriminating signal (CG-4C-04a)."""
        if not self.signal.strip():
            raise ValueError("a FailureTag must declare a non-empty discriminating signal")


# Every tag's definition. The `signal` prose is the discriminating signal from the
# `02c` §3.4 tag table, kept beside the tag so the "0 signal-less tags" rule is a
# property of the data, not of a separate document that could drift from it.
TAG_SPECS: dict[FailureTag, FailureTagSpec] = {
    FailureTag.POLICY_WRONG_ACTION: FailureTagSpec(
        axis=TagAxis.POLICY,
        derivation=TagDerivation.HUMAN,
        signal=(
            "requestedPositionAction is physically valid but task-inappropriate; "
            "zero gate intervention and zero safety events"
        ),
    ),
    FailureTag.POLICY_OUT_OF_BOUNDS: FailureTagSpec(
        axis=TagAxis.POLICY,
        derivation=TagDerivation.AUTO,
        signal=(
            "requestedPositionAction != acceptedPositionAction — a joint-limit clamp in "
            "the WP-4A-08 dual log; without that dual record this tag cannot exist"
        ),
    ),
    FailureTag.POLICY_RUNAWAY: FailureTagSpec(
        axis=TagAxis.POLICY,
        derivation=TagDerivation.AUTO,
        signal="one of the four FR-INF-043 runaway conditions tripped, driving P3 -> P8",
    ),
    FailureTag.POLICY_INVALID_OUTPUT: FailureTagSpec(
        axis=TagAxis.POLICY,
        derivation=TagDerivation.AUTO,
        signal="FR-INF-042 NaN/Inf/outlier rejection counter greater than zero",
    ),
    FailureTag.QUEUE_STARVATION: FailureTagSpec(
        axis=TagAxis.INFRA,
        derivation=TagDerivation.AUTO,
        signal="FR-INF-012 action-queue exhaustion ratio over its threshold",
    ),
    FailureTag.REMOTE_DISCONNECT: FailureTagSpec(
        axis=TagAxis.INFRA,
        derivation=TagDerivation.AUTO,
        signal=(
            "FR-INF-046 transport/session loss (a network disconnect), a distinct tag "
            "from an empty action"
        ),
    ),
    FailureTag.REMOTE_EMPTY_ACTION: FailureTagSpec(
        axis=TagAxis.INFRA,
        derivation=TagDerivation.AUTO,
        signal=(
            "FR-INF-046 live channel returned an empty action, a distinct tag from a transport loss"
        ),
    ),
    FailureTag.SAFETY_STOP: FailureTagSpec(
        axis=TagAxis.SAFETY,
        derivation=TagDerivation.AUTO,
        signal="safety-gate activation count greater than zero (FR-SIM-058 safety-stop counter)",
    ),
    FailureTag.COLLISION: FailureTagSpec(
        axis=TagAxis.SAFETY,
        derivation=TagDerivation.AUTO,
        signal="collision event count greater than zero (FR-SIM-058)",
    ),
    FailureTag.TORQUE_LIMIT: FailureTagSpec(
        axis=TagAxis.SAFETY,
        derivation=TagDerivation.AUTO,
        signal="torque-limit-reached count greater than zero (FR-SIM-058 actuatorfrcrange)",
    ),
    FailureTag.RESET_ERROR: FailureTagSpec(
        axis=TagAxis.ENVIRONMENT,
        derivation=TagDerivation.HUMAN,
        signal=(
            "human reset error — the scene initial state lies outside the collected distribution"
        ),
    ),
    FailureTag.TIMEOUT: FailureTagSpec(
        axis=TagAxis.ENVIRONMENT,
        derivation=TagDerivation.FSM,
        signal="the episode terminated in the FSM's separate TIMEOUT state (CG-4C-01c), not FAIL",
    ),
    FailureTag.AMBIGUOUS: FailureTagSpec(
        axis=TagAxis.JUDGMENT,
        derivation=TagDerivation.HUMAN,
        signal=(
            "the labeler could not decide success or failure — "
            "the WP-4C-07 auto-judge disable trigger"
        ),
    ),
}

# Load-time completeness: every tag has a spec, so a tag added without a signal fails
# at import rather than slipping past into an aggregation. This makes CG-4C-04a a
# property of the module, checked before any test runs.
if set(TAG_SPECS) != set(FailureTag):
    missing = set(FailureTag) - set(TAG_SPECS)
    raise RuntimeError(f"FailureTag(s) without a definition: {sorted(t.name for t in missing)}")


def spec_for(tag: FailureTag) -> FailureTagSpec:
    """Return the definition of a tag.

    Args:
        tag: The tag to look up.

    Returns:
        (FailureTagSpec) Its axis, derivation, and discriminating signal.
    """
    return TAG_SPECS[tag]


def machine_tags() -> frozenset[FailureTag]:
    """Return the nine tags the correlation engine auto-derives in this phase.

    Returns:
        (frozenset[FailureTag]) The AUTO-derived tags — and the exact set the engine's
        output may ever contain, so a human/FSM tag can never be fabricated by the engine.
    """
    return frozenset(
        tag for tag, spec in TAG_SPECS.items() if spec.derivation is TagDerivation.AUTO
    )


def deferred_tags() -> frozenset[FailureTag]:
    """Return the tags whose assignment is deferred to phase-2 or the WP-4C-01 FSM.

    Returns:
        (frozenset[FailureTag]) The HUMAN and FSM tags — schema slots this batch does
        not populate.
    """
    return frozenset(
        tag for tag, spec in TAG_SPECS.items() if spec.derivation is not TagDerivation.AUTO
    )
