"""Fixed values of the WP-4C-03 success-rate protocol (`02c` §3.3).

Every literal here is a decision the spec made, not a tuning knob this package
invented. The N>=20 floor, the 95% confidence level, and the self-baseline label
each cite exactly one requirement, and the plan invents no other number
(`02c` §3.3 인터페이스 계약: "계획이 다른 수를 발명하지 않는다").
"""

from __future__ import annotations

# The two-sided 95% standard-normal quantile Φ⁻¹(0.975). It is the z the Wilson
# score interval multiplies, and it is what the spec's cited arithmetic used to
# reach N=20 -> ≈±21%p and N=50 -> ≈±13.6%p (`FR-SIM-056`). Held as an exact
# constant rather than computed at runtime so the aggregator needs no SciPy and
# the reproduction check compares against a fixed number.
Z_SCORE_95 = 1.959963984540054

# The confidence level and its complement. `ALPHA` splits in two for the
# two-sided interval, so the Clopper-Pearson boundary tails each use `ALPHA / 2`.
CONFIDENCE_LEVEL = 0.95
ALPHA = 0.05
HALF_ALPHA = ALPHA / 2.0

# `NFR-PRF-050` / `FR-SIM-056`: a task needs N >= 20 trials before a success rate
# is comparable, and this is the SOLE basis of `statistically_meaningful`. Below
# it the report is emitted but flagged statistically-meaningless and no ranking is issued
# (`02c` §3.3 CG-4C-03c). The plan pins no other threshold.
N_MIN_MEANINGFUL = 20

# `FR-INF-063`: two checkpoints may not be ranked from a SINGLE execution of the
# same rollout set — nondeterministic augmentation alone swings success 5-6%p, so
# a single run's ordering is noise. The requirement forbids a single execution; the
# smallest count that is not single is two. This is the floor the requirement
# itself implies, not a fabricated repeat count — the spec pins no larger number.
MIN_INDEPENDENT_RUNS = 2

# `FR-SIM-059`: no official OpenArm sim2real baseline exists, so every number is a
# self-measured baseline and the report must say so. This exact token is what the
# renderer stamps and what CG-4C-03f greps for.
SELF_BASELINE_KIND = "self-baseline"

# The percentile the report reduces per-episode inference latency to
# (`FR-SIM-058` / `NFR-PRF-050`: inference-latency p95).
LATENCY_PERCENTILE = 95.0

# The `FR-SIM-058` report items (6) and the `NFR-PRF-050` items (4). CG-4C-03g
# requires the union of both to be present in every report; the two tuples are
# kept distinct rather than merged so the gate can prove each requirement's own
# item list is covered, not merely their union. `NFR-PRF-050`'s four are the
# co-recorded metrics; its success-rate+CI mandate is covered by SIM-058 item one.
SUCCESS_RATE_WITH_CI = "success_rate_with_ci"
EPISODE_LENGTH_MEDIAN = "episode_length_median"
COLLISION_COUNT = "collision_count"
TORQUE_LIMIT_HITS = "torque_limit_hits"
SAFETY_STOP_COUNT = "safety_stop_count"
INFERENCE_LATENCY_P95 = "inference_latency_p95"

FR_SIM_058_ITEMS = (
    SUCCESS_RATE_WITH_CI,
    EPISODE_LENGTH_MEDIAN,
    COLLISION_COUNT,
    TORQUE_LIMIT_HITS,
    SAFETY_STOP_COUNT,
    INFERENCE_LATENCY_P95,
)

NFR_PRF_050_ITEMS = (
    EPISODE_LENGTH_MEDIAN,
    COLLISION_COUNT,
    SAFETY_STOP_COUNT,
    INFERENCE_LATENCY_P95,
)

# The confidence-interval method labels the report carries and the renderer prints.
METHOD_WILSON = "wilson-95"
METHOD_CLOPPER_PEARSON = "clopper-pearson-95"

# Comparison verdicts (`compare_checkpoints`). Superiority is only ever one of the
# ordered verdicts when the interval evidence separates the two checkpoints; every
# ambiguous or ineligible case collapses to UNDETERMINED (`02c` §3.3 CG-4C-03e,
# and the sibling CG-4C-06d overlapping-CI rule this comparison already honours).
VERDICT_A_BETTER = "A_BETTER"
VERDICT_B_BETTER = "B_BETTER"
VERDICT_UNDETERMINED = "UNDETERMINED"

# Why a comparison returned UNDETERMINED, so the caller can tell "not enough runs"
# from "runs disagree within noise" from "sample too small to mean anything".
REASON_SINGLE_RUN = "single-run comparison forbidden (FR-INF-063)"
REASON_NOT_MEANINGFUL = "statistically meaningless: a run has N<20 (NFR-PRF-050)"
REASON_OVERLAPPING_CI = "Wilson 95% CIs overlap — 우열 미판정"
REASON_CI_SEPARATED = "Wilson 95% CIs are disjoint"

# Rendered flag for an N<20 report (`02c` §3.3 CG-4C-03c).
STATISTICALLY_MEANINGLESS_LABEL = "통계적으로 무의미"
