"""`EpisodeRecord` — the aggregation-input contract WP-4C-03 owns (`02c` §3.3).

This is the shape the statistics aggregator consumes, and only that. The real
rollout population that fills it — WP-4C-01 (rollout FSM) and WP-4C-02 (human
success labelling and failure-tag assignment) — is DEFERRED (`02c` §3.1/§3.2 are
Human bands). So this record is deliberately the *offline* subset: the per-episode
numbers the aggregator needs, with `success` and `failure_tags` treated as given
inputs, never fabricated here.

Two contract points matter:

- `failure_tags` are GENERIC string values, not WP-4C-04's `FailureTag` enum.
  WP-4C-03 counts tags by value (a data-join), so the two build in parallel with
  no type dependency — WP-4C-04 owns the tag definitions, WP-4C-03 only tallies
  them (`02c` §3.3/§3.4, DO-NOT-DUPLICATE). Importing the enum here would fork
  that ownership.
- `seed` is mandatory. `FR-SIM-056`/`NFR-PRF-050` require the initial-state seed
  to be recorded per episode for reproducibility; an aggregation input that
  dropped it would let an irreproducible rollout into the statistics.

The checkpoint identity an episode belongs to is NOT a field here: it is the
grouping context the aggregator is called with (a WP-4A-05 `CheckpointId`), so one
`EpisodeRecord` value is reusable across the (rollout_set, checkpoint) it is
aggregated under, and the lineage tie lives at the aggregation boundary
(`aggregator.aggregate`).
"""

from __future__ import annotations

from dataclasses import dataclass


class EpisodeRecordError(ValueError):
    """Raised when an aggregation-input episode is internally inconsistent.

    Every case is a refusal to aggregate a record that cannot be a real episode:
    a negative count, a non-positive length, or a negative latency. Refusing here
    keeps a malformed episode out of the statistics rather than letting it skew a
    median or a tail.
    """


@dataclass(frozen=True)
class EpisodeRecord:
    """One episode's offline, aggregation-relevant facts (`02c` §3.3 input).

    Frozen because an episode outcome is a recorded fact, not a mutable buffer:
    the aggregator reads many of these and must not be able to alter one.

    Attributes:
        task_id: The task this episode ran, the axis success rates are grouped by.
        seed: The recorded initial-state seed (`FR-SIM-056` reproducibility).
        success: The success label. Its origin (human / auto) is WP-4C-02's
            concern; here it is a given input the aggregator never invents.
        episode_length: Steps the episode ran, source of the length median.
        collisions: Collision events in this episode (`FR-SIM-058`).
        torque_limit_hits: Torque-limit reaches in this episode (`FR-SIM-058`).
        safety_stops: Safety-gate activations in this episode (`FR-SIM-058`).
        inference_latency_p95: This episode's own p95 policy-inference latency, in
            milliseconds (`FR-SIM-058`/`NFR-PRF-050`).
        failure_tags: Generic failure-tag values for this episode, by value — not
            WP-4C-04's enum. Empty on a success (or an unclassified failure).
    """

    task_id: str
    seed: int
    success: bool
    episode_length: int
    collisions: int
    torque_limit_hits: int
    safety_stops: int
    inference_latency_p95: float
    failure_tags: tuple[str, ...]

    def validate(self) -> None:
        """Refuse an episode that cannot be a real rollout outcome.

        Raises:
            EpisodeRecordError: On a non-positive length, any negative count, or a
                negative latency.
        """
        if self.episode_length <= 0:
            raise EpisodeRecordError(f"episode_length must be positive, got {self.episode_length}")
        for name, value in (
            ("collisions", self.collisions),
            ("torque_limit_hits", self.torque_limit_hits),
            ("safety_stops", self.safety_stops),
        ):
            if value < 0:
                raise EpisodeRecordError(f"{name} must be non-negative, got {value}")
        if self.inference_latency_p95 < 0.0:
            raise EpisodeRecordError(
                f"inference_latency_p95 must be non-negative, got {self.inference_latency_p95}"
            )
