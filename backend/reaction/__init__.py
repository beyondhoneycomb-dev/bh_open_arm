"""WP-2C-05 — collision reaction strategy and latch.

The layer that answers "the GMO confirmed a collision — now what does the arm do?"
without ever stopping the command loop (`FR-SAF-073`). It owns the six reaction
strategies (`FR-SAF-037`), the frames they send, the three safety guards on those
frames, and the latch policy — and it reuses, rather than re-implements, the Wave-1
actuation spine:

* The **latch** is `backend.actuation`'s one-way `SafetyLatch`, engaged through the
  scheduler; `latch_until_ack=true`/`auto_resume=false` are frozen (`FR-SAF-043`).
* The **stop is not a loop stop**: `STOP_HOLD = MIT(kp_orig, kd_orig, q_hold, 0,
  τ_grav)` re-sent every tick, proven on the reused scheduler + fake CAN
  (`FR-SAF-038`). `τ_grav` is the model term supplied by `WP-2B-02`/`WP-2C-01`,
  carried through — not computed here.
* **`FR-SAF-069`** gates the three feed-forward reactions (STOP_HOLD's τ_grav,
  GRAVITY_COMP, ADMITTANCE): without the torque/velocity channel they cannot exist.
* **`FR-SAF-040`** refuses any position command with `kd == 0`.
* **`FR-SAF-042`** refuses POWER_OFF without a fall warning and a double confirmation.

What is deferred here (torque-ON / real bus): the quantitative `NFR-SAF-007` hold
send-period-below-RID-9 acceptance — skipped-with-reason, re-verified by `reverify`.
"""

from __future__ import annotations

from backend.reaction.capability import (
    TorqueChannel,
    TorqueChannelUnavailableError,
    require_channels,
)
from backend.reaction.constants import (
    ADMITTANCE_GAIN,
    AUTO_RESUME_DEFAULT,
    DEFAULT_STRATEGY_NAME,
    FIXTURE_ENV_VAR,
    LATCH_UNTIL_ACK_DEFAULT,
    POWER_OFF_CAN_OPCODE,
    POWER_OFF_FALL_WARNING,
    RETRACT_ALPHA_RAD,
    RETRACT_KP_LOW,
    STOP_DECEL_RAMP_STEPS,
)
from backend.reaction.executor import (
    ReactionExecutor,
    SchedulerLike,
    stream_reaction_frames,
)
from backend.reaction.frame import (
    DecelTrajectory,
    KdZeroPositionCommandError,
    PowerOffConfirmation,
    PowerOffConfirmationError,
    PowerOffDirective,
    ReactionCommand,
    ReactionContext,
    build_reaction_command,
    resume_to_position,
)
from backend.reaction.policy import ReactionPolicy, ReactionPolicyError
from backend.reaction.reverify import (
    HoldSendPeriodVerification,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.reaction.staticcheck import find_estop_stop_recording_wiring
from backend.reaction.strategy import (
    DEFAULT_STRATEGY,
    ReactionStrategy,
    StopCategory,
    StrategyProperties,
    properties,
)

__all__ = [
    "ADMITTANCE_GAIN",
    "AUTO_RESUME_DEFAULT",
    "DEFAULT_STRATEGY",
    "DEFAULT_STRATEGY_NAME",
    "FIXTURE_ENV_VAR",
    "LATCH_UNTIL_ACK_DEFAULT",
    "POWER_OFF_CAN_OPCODE",
    "POWER_OFF_FALL_WARNING",
    "RETRACT_ALPHA_RAD",
    "RETRACT_KP_LOW",
    "STOP_DECEL_RAMP_STEPS",
    "DecelTrajectory",
    "HoldSendPeriodVerification",
    "KdZeroPositionCommandError",
    "PowerOffConfirmation",
    "PowerOffConfirmationError",
    "PowerOffDirective",
    "ReactionCommand",
    "ReactionContext",
    "ReactionExecutor",
    "ReactionPolicy",
    "ReactionPolicyError",
    "ReactionStrategy",
    "SchedulerLike",
    "StopCategory",
    "StrategyProperties",
    "TorqueChannel",
    "TorqueChannelUnavailableError",
    "build_reaction_command",
    "find_estop_stop_recording_wiring",
    "fixture_dir_from_env",
    "properties",
    "require_channels",
    "resume_to_position",
    "reverify_from_fixture",
    "stream_reaction_frames",
]
