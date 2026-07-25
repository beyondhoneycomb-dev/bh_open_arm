"""`EpisodeSignals` — the terminal signals of one episode, the correlation engine's input.

This is the aggregation-input contract the WP-4C-04 engine reads. Every field is a
signal we already hold, taken from the committed WP-4A-08 surface or the FR-SIM-058
rollout counters — nothing here is invented (`02c` §3.4 forbids invention).

The decisive field is `dual_records`: the engine derives `POLICY_OUT_OF_BOUNDS` only by
inspecting the WP-4A-08 dual log for a joint-limit clamp. Carrying the real
`DualActionRecord`s — not a reduced boolean — is what makes the tag auto-derived and
never human-assigned (CG-4C-04b): the only path to the tag is the record, so "this tag
cannot exist without the dual record" is structural. `from_detector` builds the signals
straight off a `RunawayDetector` at episode end, which is how the WP-4C-01 rollout
harness (deferred) will feed the engine.

The committed types are imported only for annotations (`from __future__ import
annotations` keeps them unevaluated at runtime), so this module stays a light data
contract and does not pull the actuation/inference runtime just to describe a shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.inference.runaway import (
        DisconnectClass,
        DualActionRecord,
        FaultKind,
        RunawayDetector,
    )


@dataclass(frozen=True)
class TaxonomyThresholds:
    """Thresholds the taxonomy needs, as parameters only — values deferred to 4C.

    Mirrors the WP-4A-08 threshold discipline (SPINE §2-6): the queue-starvation limit
    derives from a nominal rollout's exhaustion distribution, which does not exist until
    4C lands, so the type refuses a default. A caller supplies it explicitly; the only
    pre-4C caller is a test, which uses `placeholder_taxonomy_thresholds`.

    Attributes:
        queue_exhaustion_ratio_max: FR-INF-012 action-queue exhaustion ratio (0..1)
            above which the episode is tagged `QUEUE_STARVATION`.
    """

    queue_exhaustion_ratio_max: float


@dataclass(frozen=True)
class EpisodeSignals:
    """One episode's terminal signals, snapshotted for failure-tag correlation.

    Attributes:
        dual_records: The WP-4A-08 dual log for the episode; the sole source of
            `POLICY_OUT_OF_BOUNDS`. Empty when no ticks were recorded.
        fault_kind: Why the detector faulted (`RUNAWAY` / `REMOTE_DISCONNECT`), or None
            if the episode did not end in a fault.
        disconnect_class: The FR-INF-046 remote-failure class this episode saw, or None.
        nan_inf_rejections: FR-INF-042 NaN/Inf/outlier rejection count.
        queue_exhaustion_ratio: FR-INF-012 action-queue exhaustion ratio (0..1) from the
            committed `QueueMeter`.
        safety_stop_count: FR-SIM-058 safety-gate activation count (Wave 2C GMO events).
        collision_count: FR-SIM-058 collision event count.
        torque_limit_hits: FR-SIM-058 torque-limit-reached count.
    """

    dual_records: tuple[DualActionRecord, ...]
    fault_kind: FaultKind | None
    disconnect_class: DisconnectClass | None
    nan_inf_rejections: int
    queue_exhaustion_ratio: float
    safety_stop_count: int
    collision_count: int
    torque_limit_hits: int

    @classmethod
    def from_detector(
        cls,
        detector: RunawayDetector,
        queue_exhaustion_ratio: float,
        disconnect_class: DisconnectClass | None,
        safety_stop_count: int,
        collision_count: int,
        torque_limit_hits: int,
    ) -> EpisodeSignals:
        """Build signals from a `RunawayDetector` at episode end plus the rollout counters.

        The detector supplies the WP-4A-08 half (dual records, fault kind, NaN/Inf
        count); the caller supplies what the detector does not retain — the queue
        exhaustion ratio (from the meter), the remote class (from the last
        `DisconnectVerdict`), and the FR-SIM-058 rollout counters.

        Args:
            detector: The episode's detector, read before `acknowledge`/`begin_episode`
                clears its fault state.
            queue_exhaustion_ratio: The committed meter's exhaustion ratio at episode end.
            disconnect_class: The remote class the episode saw, or None.
            safety_stop_count: FR-SIM-058 safety-stop count.
            collision_count: FR-SIM-058 collision count.
            torque_limit_hits: FR-SIM-058 torque-limit count.

        Returns:
            (EpisodeSignals) The snapshotted signals for the correlation engine.
        """
        return cls(
            dual_records=detector.recorder.records,
            fault_kind=detector.fault_kind,
            disconnect_class=disconnect_class,
            nan_inf_rejections=detector.nan_inf_rejections,
            queue_exhaustion_ratio=queue_exhaustion_ratio,
            safety_stop_count=safety_stop_count,
            collision_count=collision_count,
            torque_limit_hits=torque_limit_hits,
        )


# A clearly-labelled placeholder for tests and the pre-4C harness. NOT a validated
# FR-INF-012 limit — 4C derives that from the nominal-rollout distribution (SPINE §2-6).
# It exists so the queue-starvation branch can be exercised, permissive enough that a
# healthy stream stays under it. A production path reaching for this factory is a bug.
_PLACEHOLDER_QUEUE_EXHAUSTION_RATIO_MAX = 0.5


def placeholder_taxonomy_thresholds() -> TaxonomyThresholds:
    """Return un-validated placeholder taxonomy thresholds for tests and the harness.

    Returns:
        (TaxonomyThresholds) Placeholder thresholds; not validated FR-INF-012 limits.
    """
    return TaxonomyThresholds(
        queue_exhaustion_ratio_max=_PLACEHOLDER_QUEUE_EXHAUSTION_RATIO_MAX,
    )
