"""Domain constants for the WP-2B-08 path-B bootstrap (spec 12 §2.6 path B, FR-SAF-030/SIM-034).

Path B is the conditional fallback 02b §2.1 spins up only when PG-FRIC-001 takes its negative
branch: the v2 friction model could not be identified, so gravity and Coriolis are bootstrapped
from the committed v2 MJCF inertia while friction stays uncompensated. Two non-negotiable facts
this file fixes as data:

* The operator-facing banner is always shown. Its wording follows FR-SAF-030 ("v2 미식별 — 감지
  비활성") extended with the friction-uncompensated qualifier the WP names, because path B
  compensates gravity but not the low-speed tanh static-friction knee (FR-SIM-034). This is
  safety copy for the same Korean-facing reader as docs/plan and docs/spec, so it is content in
  Korean, not a comment.
* Path B's PG-FRIC-001 outcome is FAIL_BLOCKING and only FAIL_BLOCKING. 02b §2.1/§2.3 forbid
  recording path B as a "partial success"; the outcome is a constant here so no code path can set
  it to PASS or DEGRADED_ACCEPTED.
"""

from __future__ import annotations

# The collision-detection method value FR-SAF-030 forces while the v2 friction model is
# unidentified (spec 12 `detection.method` enum). Path B never leaves this state.
DETECTION_METHOD_DISABLED = "DISABLED"

# The single legal PG-FRIC-001 outcome for path B, in the 02b §0.2 gate-state vocabulary. Path B
# is a deferral, not a pass: recording it as PASS / DEGRADED_ACCEPTED / "partial success" is the
# exact FAIL_BLOCKING defect 02b §2.1 names.
PG_FRIC_OUTCOME = "FAIL_BLOCKING"

# Always-shown banner. The headline carries the FR-SAF-030 detection-disabled statement plus the
# friction-uncompensated qualifier (CG-2B-08b); the detail states the path-B limitation
# (FR-SIM-034): gravity+Coriolis are compensated from v2 inertia but the low-speed tanh friction
# knee is not, so residual detection would false-fire near static friction.
BANNER_HEADLINE = "마찰 미보상 — 충돌 감지 비활성 (경로 B 부트스트랩)"
BANNER_DETAIL = (
    "중력·코리올리만 v2 관성(qfrc_bias)으로 보상한다. 마찰은 v2 미식별 상태이므로 "
    "저속 정지마찰(tanh 무릎)이 재현되지 않는다. 충돌 감지는 DISABLED로 강제되며 "
    "PG-FRIC-001 통과 전까지 재활성화할 수 없다."
)
