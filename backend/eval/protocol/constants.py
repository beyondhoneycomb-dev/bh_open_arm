"""Fixed values of the WP-4C-05 dual-condition protocol (`02c` §3.5).

Every literal here is a decision `02c` §3.5 made, not a knob this package invented.
The rendered strings are Korean because the report is content for the same Korean
planning corpus the WP-4C-03 renderer writes into; the exception/refusal messages
are English, matching the sibling `backend/eval/stats` modules. The English-comments
rule governs what the code says about itself, not the body of a report it renders.
"""

from __future__ import annotations

# The reference to the Wave 3C initial-state distribution the perturbation axes are
# derived from (`02c` §3.5 interface contract: the plan does not fix the perturbation
# axes — each is derived from the per-task initial-state distribution Wave 3C recorded).
# This is the anchor CG-4C-05c requires every axis to reference; an axis with no
# distribution reference is an arbitrary axis.
WAVE_3C_DISTRIBUTION_REF = "Wave 3C 초기 상태 분포"

# The exact phrase CG-4C-05c's negative branch mandates in the report when the
# generalization gap cannot be measured. The report greps for this, so it is one
# token, defined once.
GENERALIZATION_GAP_UNMEASURED = "일반화 격차 미측정"

# Why PERTURBED is deferred right now: the Wave 3C distribution has not landed, so no
# perturbation axis can be defined, so the perturbed condition cannot run and the gap
# is unmeasured (`02c` §3.5 negative branch ③ — a deferral, not a FAIL). Carries both
# the Wave 3C reference (CG-4C-05c part 1) and the unmeasured phrase (CG-4C-05c part 2).
PERTURBED_DEFERRED_REASON = (
    f"PERTURBED 조건 보류: {WAVE_3C_DISTRIBUTION_REF}가 아직 착지하지 않아 "
    f"섭동 축을 정의할 수 없다 (02c §3.5 ③ 음성분기). "
    f"{GENERALIZATION_GAP_UNMEASURED} — NOMINAL 단독으로 진행한다."
)

# The generalization gap is a DERIVED scalar and nothing more: CG-4C-05b forbids
# asserting a separate confidence interval on it, because a difference-of-two-binomials
# CI is a distinct statistic the spec grounds nowhere (`02c` §3.5 ②). This note is
# stamped beside every measured gap so the absence of a gap CI is stated, not silent.
GAP_DERIVED_NO_CI_NOTE = (
    "일반화 격차는 파생값이다 — 두 이항 비율 차이에 별도 신뢰구간을 주장하지 않는다 "
    "(02c §3.5 ②, 명세 근거 없음)."
)

# The PERTURBED reproducibility limit (`02c` §3.5 trade-off 2). Recording the seed does not
# make a perturbed set as reproducible as a nominal one — the seed does not place the
# objects, a human does — and the plan refuses to hide that. Stated in every report.
PERTURBED_REPRODUCIBILITY_LIMIT = (
    "PERTURBED 재현성 한계(대가 2): 시드를 기록해도(FR-SIM-056) "
    "시드는 물체 위치를 결정하지 않는다 — 사람이 결정한다. "
    "따라서 perturbed CI는 nominal CI보다 넓게 해석해야 하며, 그 넓이는 정량화할 수 없다."
)

# The FR-TRN-073 (c)/(d) rule the dual-condition set enforces as its axis: the two
# conditions must share the same checkpoint, trial count and success criterion, or the
# set is not a controlled comparison and its gap is meaningless (`02c` §3.5 CG-4C-05a).
SAME_SET_RULE = "FR-TRN-073 (c)/(d) — 동일 체크포인트·동일 시행 수·동일 성공 기준"

# Report section headings (`02c` §3.5 output: the per-condition report axis, which
# shows the two conditions separately).
REPORT_TITLE = "이중 조건 프로토콜 리포트 (nominal + perturbed)"
NOMINAL_SECTION_LABEL = "NOMINAL 조건"
PERTURBED_SECTION_LABEL = "PERTURBED 조건"
