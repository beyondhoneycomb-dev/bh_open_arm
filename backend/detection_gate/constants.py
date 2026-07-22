"""Domain constants for the WP-2C-02 detection activation gate (FR-SAF-029/030/001b).

Every value is a spec-given identifier or operator-facing safety copy — never a measured
threshold. The 1 kHz detection-loop target and the pattern-B 625 Hz ceiling are NOT re-declared
here: they are canon in `backend/safety_bringup/constants.py` and reused at the point they bind
(activation.py imports `DETECTION_LOOP_TARGET_HZ`), so the target lives in exactly one place.
"""

from __future__ import annotations

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

# The architecture-reopen banner (02b §3.2 WP-2C-02 negative branch, spec 12 §2.9 circular-
# frequency problem). Shown when the loop cannot reach 1 kHz on the pattern that is meant to
# (pattern A):
# no frame pattern delivers the target, so this is not an accepted downgrade but a design
# escalation, and presenting it as an accepted degrade is the forbidden silent pass (③).
REOPEN_BANNER_HEADLINE = "감지 루프 1 kHz 불성립 — 아키텍처 재개봉 필요"
REOPEN_BANNER_DETAIL = (
    "어떤 프레임 패턴으로도 1 kHz가 성립하지 않는다(12 §2.9 순환 문제). 강등 수용이 아니라 "
    "아키텍처 재검토가 필요하며, 이 상태를 강등 수용으로 넘기는 것은 금지된다."
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
