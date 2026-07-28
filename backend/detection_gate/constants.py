"""Domain constants for the WP-2C-02 detection activation gate (FR-SAF-029/030/001b, NORM-008).

Most values here are spec-given identifiers or operator-facing safety copy. Two are numbers, and
they are declared here rather than reused because they are this gate's own: the forward-Euler
stability bound and the residual-detection target rate derived from it. WP-1-06's
`DETECTION_LOOP_TARGET_HZ` (1 kHz) is a different figure with a different meaning — NORM-008
discards it as a pass/fail line — and this gate no longer reads it. The pattern-B 625 Hz ceiling
stays WP-1-06's alone: that one is a measurement input, which NORM-008 keeps.
"""

from __future__ import annotations

# The residual observer integrates forward-Euler (`backend/gmo/observer.py:118`), so the residual
# error obeys `e[n+1] = (1 - K*dt)*e[n]` and decays only while `|1 - K*dt| < 1`, i.e.
# `0 < K*dt < 2`. Strict at the upper end: driven at exactly `K*dt == 2` the real observer locks
# into a two-cycle (0 / 10 Nm on a 5 Nm step) that crosses any threshold every other tick and
# never reaches the step.
FORWARD_EULER_STABILITY_BOUND = 2.0

# The detection loop rate below which residual-based detection stops being valid — not a pass
# line. At the NORM-011 gain K = 90 (`backend/gmo/constants.py:34`) the bound above puts the floor
# at 45 Hz; 100 Hz gives K*dt = 0.9 and the residual reaches a 5 Nm step in three ticks with no
# overshoot, while 10 Hz (K*dt = 9) walks 45 -> -315 -> 2565 -> -20475. The CAN-FD budget of
# 625 Hz (32 frames per LeRobot cycle) leaves room above it. Replaces the 1 kHz of NFR-SAF-001,
# which NORM-008 discards as physically unreachable.
RESIDUAL_DETECTION_TARGET_HZ = 100.0

# The loop period the target implies, derived so the rate above stays the single source of the
# figure. `gain_converges`/`assert_gain_converges` are stated in `detection_dt_s`, so this is the
# same operating point in the unit those two read.
RESIDUAL_DETECTION_TARGET_PERIOD_S = 1.0 / RESIDUAL_DETECTION_TARGET_HZ

# The PG-FRIC-001 gate whose PASS is the sole key to detection activation (02b §3.0,
# FR-SAF-030). Detection activation is a function of this verdict and nothing else.
PG_FRIC_001 = "PG-FRIC-001"

# Gate-state names from the 02b §0.2 state machine. That document is canonical for the
# vocabulary; code names the states it uses as English identifiers, the same convention the
# sibling gates follow (torque_bringup, rtbench, safety_bringup each declare the states they
# emit). Only the two this gate emits or tests against are named.
GATE_STATE_PASS = "PASS"
GATE_STATE_DEGRADED_ACCEPTED = "DEGRADED_ACCEPTED"

# The always-shown detection-disabled banner (FR-SAF-029/030, 02b §3.0). Korean safety copy for
# the same operator the docs/plan and docs/spec address — this is content, not a comment. Shown
# whenever PG-FRIC-001 has not passed; collision detection stays DISABLED until it does.
DISABLED_BANNER_HEADLINE = "v2 미식별 — 충돌 감지 비활성"
DISABLED_BANNER_DETAIL = (
    "충돌 감지는 DISABLED로 강제된다. 활성화는 PG-FRIC-001(마찰 식별) PASS의 함수이며, "
    "통과 전까지 활성화 UI·API가 코드 레벨로 잠긴다."
)

# The architecture-reopen banner (02b §3.2 WP-2C-02 negative branch). Shown when the achievable
# loop rate cannot satisfy `K*dt < bound` for the configured gain: the residual does not converge
# at all, so detection is not slow, it is invalid. That is a design escalation — either the loop
# gets faster or K comes down — and presenting it as an accepted degrade is the forbidden silent
# pass (③). The detail is a template because the escalation is only actionable if the operator
# sees which four numbers produced it.
REOPEN_BANNER_HEADLINE = "감지 루프 수렴 조건 불성립 — 아키텍처 재개봉 필요"
REOPEN_BANNER_DETAIL_TEMPLATE = (
    "관측기가 전진 오일러 적분이라 K x dt < {bound} 에서만 잔차가 수렴한다. 현재 "
    "K = {observer_gain:.1f}, 루프 주기 {period_ms:.2f} ms 로 K x dt = {gain_period_product:.2f} "
    "이며, 이 이득에는 최소 {floor_hz:.1f} Hz 가 필요하다. 강등 수용이 아니라 아키텍처 "
    "재검토가 필요하며, 이 상태를 강등 수용으로 넘기는 것은 금지된다."
)

# The degraded banner carries the measured effective latency and the lowered speed cap, so it is
# a template the formatter fills (banner.py), not a fixed string. `{latency_ms}` is the ≈1/f
# effective detection delay the UI must show (FR-SAF-001b); `{cap_percent}` is the jog/teleop
# speed-cap fraction the downgrade actually enforces, without which the display is an alibi
# (02b §3.3: a display is not a defense).
DEGRADED_BANNER_TEMPLATE = (
    "충돌 감지 강등(DEGRADED_ACCEPTED) — 실효 검출 지연 {latency_ms:.2f} ms, "
    "조그·텔레옵 속도 상한 {cap_percent:.1f}%로 하향"
)
