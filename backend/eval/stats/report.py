"""`SuccessRateReport` — the WP-4C-03 output contract, renderer, and self-baseline lock.

The report carries the union of `FR-SIM-058`'s six items and `NFR-PRF-050`'s four
(`02c` §3.3 인터페이스 계약), keyed to a WP-4A-05 lineage `CheckpointId` so every
number is attributable to the immutable eight-element snapshot that produced the
checkpoint — a success rate with no lineage is not representable here.

Two invariants are enforced structurally, not by convention:

- **Self-baseline only** (`FR-SIM-059`). `baseline_kind` is fixed to
  `SELF_BASELINE_KIND`; construction refuses any other value, and there is no
  field anywhere in this contract for an external/official baseline. A number
  cannot be reported as measured against a baseline that does not exist.
- **N>=20 is the only meaningfulness basis** (`NFR-PRF-050`/`FR-SIM-056`).
  `statistically_meaningful` must equal `n_trials >= N_MIN_MEANINGFUL`; the
  contract admits no other rule, and the renderer flags a sub-threshold report
  "통계적으로 무의미" (CG-4C-03c).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from backend.eval.stats.constants import (
    COLLISION_COUNT,
    EPISODE_LENGTH_MEDIAN,
    FR_SIM_058_ITEMS,
    INFERENCE_LATENCY_P95,
    N_MIN_MEANINGFUL,
    NFR_PRF_050_ITEMS,
    SAFETY_STOP_COUNT,
    SELF_BASELINE_KIND,
    STATISTICALLY_MEANINGLESS_LABEL,
    SUCCESS_RATE_WITH_CI,
    TORQUE_LIMIT_HITS,
)
from backend.eval.stats.intervals import ConfidenceInterval

# WP-4A-05 lineage consumption: the checkpoint identity a report is keyed by is the
# lineage store's `CheckpointId`, so the statistics ride the same identity the
# eight-element snapshot does (`02c` §3.3 input: WP-4A-05 lineage). This import is also
# what backs the WP-4A-05 -> WP-4C-03 downstream edge in the reference graph
# (`06` §5.6 / CI-16) — the edge is a real static reference, not a phantom.
from backend.training.lineage import CheckpointId


class SuccessRateReportError(ValueError):
    """Raised when a report would violate a WP-4C-03 invariant at construction.

    The `FAIL_BLOCKING` cases: a `baseline_kind` other than self-baseline
    (`FR-SIM-059`), a `statistically_meaningful` flag that disagrees with the
    N>=20 rule (`NFR-PRF-050`), counts outside `0 <= n_success <= n_trials`, or a
    Clopper-Pearson interval attached off the boundary (`02c` §3.3).
    """


@dataclass(frozen=True)
class SuccessRateReport:
    """One (rollout set, checkpoint) success-rate report (`02c` §3.3 인터페이스 계약).

    Frozen: a report is a computed summary of a fixed episode set. Every field the
    contract names is present; none is invented. `ci_clopper_pearson_95` is the one
    optional field — present only on the p̂∈{0,1} boundary, `None` otherwise.

    Attributes:
        rollout_set_id: The rollout set these episodes came from.
        checkpoint: The WP-4A-05 lineage identity of the evaluated checkpoint.
        n_trials: Number of episodes aggregated.
        n_success: Number of successful episodes.
        point_estimate: `n_success / n_trials`.
        ci_wilson_95: The canonical Wilson 95% interval (always present).
        ci_clopper_pearson_95: The Clopper-Pearson 95% interval, present ONLY when
            `n_success ∈ {0, n_trials}`; `None` elsewhere.
        statistically_meaningful: `n_trials >= N_MIN_MEANINGFUL`, and nothing else.
        seeds: The per-episode initial-state seeds (`FR-SIM-056` reproducibility).
        episode_length_median: Median episode length (`FR-SIM-058`/`NFR-PRF-050`).
        collision_count: Total collisions (`FR-SIM-058`/`NFR-PRF-050`).
        torque_limit_hits: Total torque-limit reaches (`FR-SIM-058`).
        safety_stop_count: Total safety-gate activations (`FR-SIM-058`/`NFR-PRF-050`).
        inference_latency_p95: p95 of per-episode inference-latency p95s, in ms
            (`FR-SIM-058`/`NFR-PRF-050`).
        failure_tag_counts: Generic failure-tag value -> count (the WP-4C-04
            data-join, by value, no enum import).
        baseline_kind: Fixed to `SELF_BASELINE_KIND` (`FR-SIM-059`).
    """

    rollout_set_id: str
    checkpoint: CheckpointId
    n_trials: int
    n_success: int
    point_estimate: float
    ci_wilson_95: ConfidenceInterval
    ci_clopper_pearson_95: ConfidenceInterval | None
    statistically_meaningful: bool
    seeds: tuple[int, ...]
    episode_length_median: float
    collision_count: int
    torque_limit_hits: int
    safety_stop_count: int
    inference_latency_p95: float
    failure_tag_counts: Mapping[str, int]
    baseline_kind: str

    @property
    def checkpoint_hash(self) -> str:
        """The report's `checkpoint_hash` — the lineage checkpoint identity as text.

        `02c` §3.3 names the field `checkpoint_hash`; the lineage identity is the
        `(output_dir, step)` pair, rendered here as one stable string so the report
        exposes the contract's field name without forking the lineage identity.

        Returns:
            (str) `"<output_dir>@<step>"`.
        """
        return f"{self.checkpoint.output_dir}@{self.checkpoint.step}"

    def validate(self) -> None:
        """Enforce the WP-4C-03 invariants that construction must not skip.

        Raises:
            SuccessRateReportError: On any invariant violation (see class docstring).
        """
        if self.baseline_kind != SELF_BASELINE_KIND:
            raise SuccessRateReportError(
                f"baseline_kind must be {SELF_BASELINE_KIND!r} — no official OpenArm sim2real "
                f"baseline exists (FR-SIM-059); got {self.baseline_kind!r}"
            )
        if self.n_trials <= 0:
            raise SuccessRateReportError(f"n_trials must be positive, got {self.n_trials}")
        if not 0 <= self.n_success <= self.n_trials:
            raise SuccessRateReportError(
                f"n_success must satisfy 0 <= n_success <= n_trials; got n_success="
                f"{self.n_success}, n_trials={self.n_trials}"
            )
        if self.statistically_meaningful != (self.n_trials >= N_MIN_MEANINGFUL):
            raise SuccessRateReportError(
                "statistically_meaningful must equal (n_trials >= "
                f"{N_MIN_MEANINGFUL}); got flag={self.statistically_meaningful} for "
                f"n_trials={self.n_trials}. N>=20 is the only basis (NFR-PRF-050)."
            )
        on_boundary = self.n_success == 0 or self.n_success == self.n_trials
        if self.ci_clopper_pearson_95 is not None and not on_boundary:
            raise SuccessRateReportError(
                "ci_clopper_pearson_95 is set off the boundary; Clopper-Pearson is reported only "
                "for n_success in {0, n_trials} (02c §3.3)"
            )

    def item_values(self) -> dict[str, float]:
        """Return the `FR-SIM-058`+`NFR-PRF-050` items as a name->value map.

        The single source the renderer and the completeness check both read, so
        "the report contains item X" means one thing. Every key in
        `FR_SIM_058_ITEMS` and `NFR_PRF_050_ITEMS` is present here by construction;
        CG-4C-03g verifies exactly that.

        Returns:
            (dict[str, float]) Every required report item and its numeric value.
        """
        return {
            SUCCESS_RATE_WITH_CI: self.point_estimate,
            EPISODE_LENGTH_MEDIAN: self.episode_length_median,
            COLLISION_COUNT: float(self.collision_count),
            TORQUE_LIMIT_HITS: float(self.torque_limit_hits),
            SAFETY_STOP_COUNT: float(self.safety_stop_count),
            INFERENCE_LATENCY_P95: self.inference_latency_p95,
        }

    def missing_items(self) -> tuple[str, ...]:
        """Required items (`FR-SIM-058` ∪ `NFR-PRF-050`) absent from `item_values`.

        Returns:
            (tuple[str, ...]) The missing item names; empty when the report is
                complete (the normal case — completeness is structural).
        """
        present = set(self.item_values())
        required = set(FR_SIM_058_ITEMS) | set(NFR_PRF_050_ITEMS)
        return tuple(sorted(required - present))

    def render(self) -> str:
        """Render the human-readable report (`02c` §3.3 산출: 리포트 렌더러).

        The rendered text is report content for the Korean planning corpus, so its
        body is Korean while this docstring stays English (the same split the
        registry reconciliation report uses). Guarantees the acceptance gates read:

        - it stamps the self-baseline label and references no external baseline
          (CG-4C-03f);
        - it prints every `FR-SIM-058`+`NFR-PRF-050` item (CG-4C-03g);
        - it flags a sub-threshold report statistically-meaningless (CG-4C-03c);
        - it prints Wilson always and Clopper-Pearson only on the boundary.

        Returns:
            (str) The rendered report.
        """
        wilson = self.ci_wilson_95
        lines = [
            "성공률 리포트 (self-baseline)",
            f"기준선 종류: {self.baseline_kind}",
            f"롤아웃 세트: {self.rollout_set_id}",
            f"체크포인트: {self.checkpoint_hash}",
            f"시행 수 N: {self.n_trials}",
            f"성공 수: {self.n_success}",
            f"점추정 성공률: {self.point_estimate:.4f}",
            f"Wilson 95% CI: [{wilson.lower:.4f}, {wilson.upper:.4f}] (±{wilson.half_width:.4f})",
        ]
        if self.ci_clopper_pearson_95 is not None:
            cp = self.ci_clopper_pearson_95
            lines.append(f"Clopper-Pearson 95% CI (경계 병기): [{cp.lower:.4f}, {cp.upper:.4f}]")
        if not self.statistically_meaningful:
            lines.append(
                f"{STATISTICALLY_MEANINGLESS_LABEL}: N<{N_MIN_MEANINGFUL} — 우열 판정 미출력"
            )
        lines.extend(
            [
                f"에피소드 길이 중앙값: {self.episode_length_median:.1f}",
                f"충돌 횟수: {self.collision_count}",
                f"토크 한계 도달 횟수: {self.torque_limit_hits}",
                f"안전정지 발동 횟수: {self.safety_stop_count}",
                f"추론 지연 p95(ms): {self.inference_latency_p95:.3f}",
                f"시드: {list(self.seeds)}",
                f"실패 태그 집계: {dict(self.failure_tag_counts)}",
            ]
        )
        return "\n".join(lines)
