"""Named parameters of the collision-reaction layer (WP-2C-05).

Every literal the reaction logic depends on is named here, so the one place a
threshold, gain, or CAN opcode is decided is the one place it is read. The values
that are physically or operationally *deferred* say so: the RID-9 hold-refresh
deadline behind `NFR-SAF-007` is `[결정필요]` (the factory `TIMEOUT` is unread on
this host), so the reaction layer carries the *shape* of the check — a maximum
inter-send interval that must stay below the deadline — and defers the number to
the real-fixture re-verification hook (`reverify`).
"""

from __future__ import annotations

# The default reaction (`FR-SAF-037`): IEC 60204-1 stop category 2, power and CAN
# kept live, no fall. Named as the string the strategy enum resolves, so a config
# that omits `reaction.mode` lands here rather than on a fall-prone category.
DEFAULT_STRATEGY_NAME = "STOP_HOLD"

# The reaction latch defaults (`FR-SAF-043`): a collision reaction latches and never
# auto-resumes; only an explicit operator acknowledge clears it. These are frozen as
# the policy contract, not tunable knobs — a policy that sets either the other way is
# refused at construction (see `policy.ReactionPolicy`).
LATCH_UNTIL_ACK_DEFAULT = True
AUTO_RESUME_DEFAULT = False

# RETRACT geometry (`FR-SAF-037` §2.10): retreat opposite the residual direction r̂
# by `RETRACT_ALPHA_RAD` radians of joint travel, with a lowered stiffness so the
# retreat is compliant rather than a stiff yank. Bootstrap values — the retreat
# distance and softness are tuned on the rig, not fixed here.
RETRACT_ALPHA_RAD = 0.1
RETRACT_KP_LOW = 10.0

# ADMITTANCE gain C (`FR-SAF-037` §2.10): the residual-to-velocity-command scale that
# turns a joint-torque residual into a yielding velocity `dq_cmd = C·r`. Bootstrap
# value; the rig sets the operational one.
ADMITTANCE_GAIN = 0.05

# POWER_OFF (`FR-SAF-042`): stop category 0 is `disable_all()` = CAN broadcast `0xFD`.
# There is no holding brake, so it is expressed as this opcode directive rather than a
# `disable_torque()` call, keeping the reaction tree free of the banned stop-path
# symbol (`04` NFR-MAN-002) while still naming the physical action.
POWER_OFF_CAN_OPCODE = 0xFD

# The `FR-SAF-042` fall warning shown before a POWER_OFF is confirmed. The double
# confirmation is enforced structurally (`frame.PowerOffConfirmation`); this is the
# text that must accompany it.
POWER_OFF_FALL_WARNING = (
    "POWER_OFF (stop category 0) cuts torque with no holding brake: the arm falls "
    "under gravity. This requires an explicit fall-warning acknowledgement and a "
    "separate confirmation before it is applied (FR-SAF-042)."
)

# STOP_DECEL (`FR-SAF-037` §2.10, stop category 1): ramp the commanded velocity to
# zero over this many steps before the terminal power-off is authorized. A decel
# trajectory is position frames whose per-step travel shrinks to zero; the count is a
# bootstrap shape, refined against the measured loop rate.
STOP_DECEL_RAMP_STEPS = 10

# Environment variable naming a directory of real candump captures for the deferred
# `NFR-SAF-007` re-verification (max hold-send interval < RID-9 `TIMEOUT`). Unset on
# this host, so the hold-send-period acceptance is skipped-with-reason, never asserted.
FIXTURE_ENV_VAR = "OPENARM_REACTION_REAL_FIXTURE"
