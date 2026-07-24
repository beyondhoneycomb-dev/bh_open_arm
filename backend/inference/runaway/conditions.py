"""The four runaway conditions, each with its own counter so none masks another.

`FR-INF-043` lists four independent runaway conditions, and the failure mode the
negative branch (`02c` §1.8) forbids is *one condition masking another*: if the
first trip short-circuited evaluation, an injected clip-saturation runaway could
hide a concurrent delta-q runaway and the 4C taxonomy would mis-attribute the
cause. So every condition is evaluated every tick and advances **its own** counter
regardless of the others; the biting set this tick is their union, and the detector
records which condition tripped *first* without ever skipping the rest.

Two of the four are consecutive-window conditions (① clip ratio over `clip_window`
consecutive ticks, ② per-tick joint jump over `runaway_ticks` consecutive ticks);
two are instantaneous ratios (③ EE speed over its limit, ④ queue-exhaustion ratio
over its limit). All four are metered against the parameterised thresholds only —
this module asserts no validated value (SPINE §2-6, see `thresholds`).

All four map to one canonical error code, `OA-INF-003` "inference runaway (limit
violation)" (`14` §2.10). The *code* is uniform because the registry gives runaway
one code; the *condition* is distinguished by the `RunawayCondition` member the
detector records as the first trigger, so attribution survives without inventing an
unregistered code.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.inference.runaway.thresholds import RunawayThresholds
from contracts.errors import codes

# All four conditions are the one registered runaway code (`14` §2.10). The
# per-condition attribution lives in `RunawayCondition`, not in a second code — the
# registry has exactly one runaway code and this band invents none.
RUNAWAY_ERROR_CODE = codes.OA_INF_003


class RunawayCondition(Enum):
    """The four `FR-INF-043` runaway conditions, named so the first trigger is attributable."""

    CLIP_RATIO = "clip_ratio"
    DELTA_Q = "delta_q"
    EE_VELOCITY = "ee_velocity"
    QUEUE_STARVATION = "queue_starvation"


# A fixed order used only to pick the recorded *first* trigger when several
# conditions bite on the same tick. It does not gate evaluation — every condition is
# always evaluated — it only makes "first trigger" deterministic for the audit.
CONDITION_PRIORITY: tuple[RunawayCondition, ...] = (
    RunawayCondition.CLIP_RATIO,
    RunawayCondition.DELTA_Q,
    RunawayCondition.EE_VELOCITY,
    RunawayCondition.QUEUE_STARVATION,
)


@dataclass(frozen=True)
class ConditionSignals:
    """One tick's runaway signals, snapshotted for evaluation.

    Attributes:
        clip_ratio: Fraction of joints clamped this tick (condition ①), 0..1.
        delta_q: Largest per-tick joint-position jump this tick, degrees (condition ②).
        ee_velocity: End-effector speed this tick, or None when unmeasured — a None
            never trips condition ③ (an absent signal is not a violation).
        starvation_ratio: Action-queue exhaustion ratio so far (condition ④), 0..1,
            read from the committed `QueueMeter`.
    """

    clip_ratio: float
    delta_q: float
    ee_velocity: float | None
    starvation_ratio: float


class RunawayConditions:
    """Evaluates all four conditions per tick, each advancing its own counters.

    Ownership: the detector holds one of these for the running episode. State is the
    per-condition consecutive run (for the two windowed conditions) and the
    per-condition trigger tally. `reset` clears both at episode start (`FR-INF-066`).
    """

    def __init__(self, thresholds: RunawayThresholds) -> None:
        """Bind the evaluator to the parameterised thresholds.

        Args:
            thresholds: The four `FR-INF-043` thresholds (parameters, not validated
                values in this band).
        """
        self._thresholds = thresholds
        self._consecutive: dict[RunawayCondition, int] = {}
        self._triggers: dict[RunawayCondition, int] = {}
        self.reset()

    def consecutive(self, condition: RunawayCondition) -> int:
        """Current consecutive over-threshold run for a windowed condition.

        Args:
            condition: The condition to read.

        Returns:
            (int) Consecutive over-threshold ticks (always 0 for the two
            instantaneous conditions).
        """
        return self._consecutive[condition]

    def trigger_count(self, condition: RunawayCondition) -> int:
        """How many ticks this specific condition has bitten (its own counter).

        Args:
            condition: The condition to read.

        Returns:
            (int) Independent trigger tally for that condition — the counter the
            no-masking gate (CG-4A-08a) asserts advances per condition.
        """
        return self._triggers[condition]

    def evaluate(self, signals: ConditionSignals) -> frozenset[RunawayCondition]:
        """Evaluate every condition and return the set that bit this tick.

        Each condition updates its own consecutive run and trigger tally; none is
        skipped because another already tripped. The returned set is the union of
        all conditions biting this tick.

        Args:
            signals: This tick's snapshotted signals.

        Returns:
            (frozenset[RunawayCondition]) The conditions that tripped this tick.
        """
        biting: set[RunawayCondition] = set()
        if self._window_bites(
            RunawayCondition.CLIP_RATIO,
            signals.clip_ratio > self._thresholds.clip_ratio_max,
            self._thresholds.clip_window,
        ):
            biting.add(RunawayCondition.CLIP_RATIO)
        if self._window_bites(
            RunawayCondition.DELTA_Q,
            signals.delta_q > self._thresholds.delta_q_max,
            self._thresholds.runaway_ticks,
        ):
            biting.add(RunawayCondition.DELTA_Q)
        ee_velocity = signals.ee_velocity
        if ee_velocity is not None and ee_velocity > self._thresholds.ee_velocity_max:
            biting.add(RunawayCondition.EE_VELOCITY)
        if signals.starvation_ratio > self._thresholds.starvation_ratio_max:
            biting.add(RunawayCondition.QUEUE_STARVATION)

        for condition in biting:
            self._triggers[condition] += 1
        return frozenset(biting)

    def first_trigger(self, biting: frozenset[RunawayCondition]) -> RunawayCondition | None:
        """Pick the deterministic first trigger among the conditions that bit.

        Args:
            biting: The conditions that tripped this tick.

        Returns:
            (RunawayCondition | None) The highest-priority biting condition, or None
            when the set is empty. Recording this — not suppressing the others — is
            how the audit names a cause without one condition masking another.
        """
        for condition in CONDITION_PRIORITY:
            if condition in biting:
                return condition
        return None

    def reset(self) -> None:
        """Clear consecutive runs and trigger tallies (episode start)."""
        self._consecutive = dict.fromkeys(RunawayCondition, 0)
        self._triggers = dict.fromkeys(RunawayCondition, 0)

    def _window_bites(self, condition: RunawayCondition, over_threshold: bool, window: int) -> bool:
        """Advance a windowed condition's consecutive run and report whether it trips.

        Args:
            condition: The windowed condition (① or ②).
            over_threshold: Whether this tick's signal exceeded the threshold.
            window: Consecutive over-threshold ticks required to trip.

        Returns:
            (bool) True when the consecutive run has reached the window.
        """
        if over_threshold:
            self._consecutive[condition] += 1
        else:
            self._consecutive[condition] = 0
        return self._consecutive[condition] >= window
