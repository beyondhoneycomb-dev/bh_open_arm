"""The four runaway thresholds — parameters only, values deferred to 4C (SPINE §2-6).

`FR-INF-043` names four thresholds — `clip_ratio_max`, `clip_window`,
`runaway_ticks`, `starvation_ratio_max` — and this band deliberately does **not**
pin their values. They derive from the *normal* distribution of a nominal rollout
(clip ratio, per-tick joint jump, EE speed, queue starvation), and that
distribution does not exist until 4C lands (`02c` §1.8 임계값 규율). Choosing a
number now would be a guess wearing a target's clothes.

So the contract of this module is: the thresholds are **required constructor
arguments with no defaults**. Production code cannot fall through to an unvalidated
default, because there is none to fall through to — a caller must supply values,
and the only caller that legitimately does so before 4C is the metering/fault
harness, which supplies clearly-labelled placeholders through
`metering_placeholder_thresholds`. That factory's numbers are not production
thresholds and say so; they exist to prove the meters and the four conditions bite,
not to assert a validated limit.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunawayThresholds:
    """The four `FR-INF-043` thresholds, every one a required parameter (no default).

    The absence of defaults is the discipline (SPINE §2-6): a validated value does
    not exist in this band, so the type refuses to invent one. 4C derives each from
    the nominal-rollout distribution and confirms it; until then a caller supplies
    metering placeholders explicitly.

    Attributes:
        clip_ratio_max: Condition ①. Fraction of joints clamped this tick above
            which the tick counts toward the clip window (0..1).
        clip_window: Condition ①. Consecutive over-`clip_ratio_max` ticks that trip
            the condition.
        delta_q_max: Condition ②. Per-tick joint-position jump (degrees) above which
            the tick counts toward the runaway window.
        runaway_ticks: Condition ②. Consecutive over-`delta_q_max` ticks that trip
            the condition.
        ee_velocity_max: Condition ③. End-effector speed above which the condition
            trips (units are the caller's EE-speed metric; the detector compares, it
            does not compute forward kinematics).
        starvation_ratio_max: Condition ④. Action-queue exhaustion ratio (starved
            ticks / total, from the committed `QueueMeter`) above which the condition
            trips (0..1).
    """

    clip_ratio_max: float
    clip_window: int
    delta_q_max: float
    runaway_ticks: int
    ee_velocity_max: float
    starvation_ratio_max: float


def metering_placeholder_thresholds() -> RunawayThresholds:
    """Return clearly-labelled placeholder thresholds for metering and fault tests.

    These are NOT validated `FR-INF-043` limits and must never be shipped as if they
    were (SPINE §2-6): 4C derives the real values from the nominal-rollout
    distribution. They exist so the four conditions and the meters can be exercised
    — permissive enough that a healthy stream does not trip them, tight enough that
    an injected fault does. A production path that reaches for this factory is a bug.

    Returns:
        (RunawayThresholds) Un-validated placeholder thresholds for the harness.
    """
    return RunawayThresholds(
        clip_ratio_max=_PLACEHOLDER_CLIP_RATIO_MAX,
        clip_window=_PLACEHOLDER_CLIP_WINDOW,
        delta_q_max=_PLACEHOLDER_DELTA_Q_MAX_DEG,
        runaway_ticks=_PLACEHOLDER_RUNAWAY_TICKS,
        ee_velocity_max=_PLACEHOLDER_EE_VELOCITY_MAX,
        starvation_ratio_max=_PLACEHOLDER_STARVATION_RATIO_MAX,
    )


# Placeholder magnitudes for the metering/fault harness ONLY. Their provenance is
# "chosen so a synthetic healthy stream stays under and an injected fault goes over",
# not "measured from a nominal rollout" — the latter is 4C's job. They are named,
# not inlined, so the one place they live is the one place their un-validated status
# is documented.
_PLACEHOLDER_CLIP_RATIO_MAX = 0.25
_PLACEHOLDER_CLIP_WINDOW = 3
_PLACEHOLDER_DELTA_Q_MAX_DEG = 20.0
_PLACEHOLDER_RUNAWAY_TICKS = 3
_PLACEHOLDER_EE_VELOCITY_MAX = 1.0
_PLACEHOLDER_STARVATION_RATIO_MAX = 0.5
