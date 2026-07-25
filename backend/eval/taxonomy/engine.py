"""The correlation engine — auto-derives the nine machine tags from committed signals.

`02c` §3.4 names a mitigation: the auto-derivable tags are not asked of a human. This engine is that
mitigation: given one episode's `EpisodeSignals`, it derives the nine machine tags from
the WP-4A-08 dual log / runaway / disconnect signals and the FR-SIM-058 counters, and
returns the set that fired. It never returns a HUMAN or FSM tag — its output is a subset
of `machine_tags()` by construction, so no code path here can fabricate a human tag
(the phase-2 deferral).

Two derivations carry load-bearing invariants:

- `POLICY_OUT_OF_BOUNDS` is read **only** from the dual log, and only when the gate
  clamped for a joint limit. A NaN/Inf reject also leaves requested != accepted in the
  record (the held pose replaced the non-finite request), so `clamp_detected` alone
  would mis-tag a reject as out-of-bounds; keying on `ClampReason.JOINT_LIMIT`
  separates the genuine clamp from the reject, which is tagged `POLICY_INVALID_OUTPUT`.
- `REMOTE_DISCONNECT` and `REMOTE_EMPTY_ACTION` stay distinct (CG-4C-04c). Network/
  session losses (transport, stale) are one tag via the committed
  `is_network_disconnect`; an empty action is the other. A `QUEUE_WAIT_TIMEOUT` is a
  live-channel queue-wait — neither a disconnect nor an empty action — so it yields no
  phase-1 remote tag.

Multiple tags per episode are expected (CG-4C-04e): a failure rarely has one cause.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.eval.taxonomy.tags import FailureTag
from backend.inference.runaway import DisconnectClass, FaultKind, is_network_disconnect
from contracts.action import ClampReason

if TYPE_CHECKING:
    from collections.abc import Sequence

    from backend.eval.taxonomy.signals import EpisodeSignals, TaxonomyThresholds
    from backend.inference.runaway import DualActionRecord

# A counter value that means "the event happened at least once". Named so the
# occurred-vs-not intent reads at every call site rather than as a bare literal.
_ANY_OCCURRENCE = 0


class CorrelationEngine:
    """Derives the nine machine failure tags from one episode's committed signals.

    Ownership: stateless apart from the thresholds it was built with; one engine can
    correlate any number of episodes. It reads signals and returns tags; it holds no
    episode state and mutates nothing.
    """

    def __init__(self, thresholds: TaxonomyThresholds) -> None:
        """Bind the engine to the taxonomy thresholds.

        Args:
            thresholds: The FR-INF-012 queue-starvation limit (a parameter, not a
                validated value in this band).
        """
        self._thresholds = thresholds

    def correlate(self, signals: EpisodeSignals) -> frozenset[FailureTag]:
        """Return the machine tags this episode's signals fire.

        Args:
            signals: The episode's terminal signals.

        Returns:
            (frozenset[FailureTag]) The auto-derived tags; always a subset of
            `machine_tags()`, possibly empty, possibly several (CG-4C-04e).
        """
        tags: set[FailureTag] = set()

        if self._joint_limit_clamped(signals.dual_records):
            tags.add(FailureTag.POLICY_OUT_OF_BOUNDS)
        if signals.fault_kind is FaultKind.RUNAWAY:
            tags.add(FailureTag.POLICY_RUNAWAY)
        if signals.nan_inf_rejections > _ANY_OCCURRENCE:
            tags.add(FailureTag.POLICY_INVALID_OUTPUT)
        if signals.queue_exhaustion_ratio > self._thresholds.queue_exhaustion_ratio_max:
            tags.add(FailureTag.QUEUE_STARVATION)

        disconnect = signals.disconnect_class
        if disconnect is not None:
            if is_network_disconnect(disconnect):
                tags.add(FailureTag.REMOTE_DISCONNECT)
            elif disconnect is DisconnectClass.EMPTY_ACTION:
                tags.add(FailureTag.REMOTE_EMPTY_ACTION)
            # QUEUE_WAIT_TIMEOUT: a live-channel queue-wait, not a disconnect nor an
            # empty action, so it yields no phase-1 remote tag (the taxonomy is revised
            # after 4C lands, per 02c §3.4 workflow-shape row).

        if signals.safety_stop_count > _ANY_OCCURRENCE:
            tags.add(FailureTag.SAFETY_STOP)
        if signals.collision_count > _ANY_OCCURRENCE:
            tags.add(FailureTag.COLLISION)
        if signals.torque_limit_hits > _ANY_OCCURRENCE:
            tags.add(FailureTag.TORQUE_LIMIT)

        return frozenset(tags)

    @staticmethod
    def _joint_limit_clamped(records: Sequence[DualActionRecord]) -> bool:
        """Whether any dual record shows a genuine joint-limit clamp.

        A record where the gate clamped the request for a joint limit is the sole
        signal for `POLICY_OUT_OF_BOUNDS`. A NaN-reject held record also has
        `clamp_detected` True but carries `ClampReason.NONE`, so it is excluded here and
        picked up by the NaN/Inf counter instead.

        Args:
            records: The episode's WP-4A-08 dual log.

        Returns:
            (bool) True when at least one record is a joint-limit clamp.
        """
        return any(
            record.clamp_detected and record.safety_override.clamp_reason is ClampReason.JOINT_LIMIT
            for record in records
        )
