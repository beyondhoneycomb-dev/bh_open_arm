"""Named quantities for gravity-compensated Freedrive (WP-2D-03, spec 04 FR-MAN-029/030/035).

Freedrive path (C) commands ``(kp=0, kd=kd_freedrive, q, dq=0, tau=tau_grav+tau_fric)`` per
joint (FR-MAN-030). The gains here are the two ends of that command: ``FREEDRIVE_KP = 0`` makes
position inert so the arm is free to be hand-guided, and ``kd_freedrive`` is the small damping
that suppresses oscillation without resisting the guide. Both stay inside the MIT encoder bands
``kp in [0,500]`` / ``kd in [0,5]`` the gateway validates, so a gain written here can never be a
value the encoder would silently wrap.

The peak-torque envelope is NOT redefined here — it belongs to the gateway/calibration owner and
arrives as a ``SafetyLimits`` the effort check and the gateway share, so there is one source for
the actuator effort a saturation check and a torque clamp both read.
"""

from __future__ import annotations

from backend.actuation.config import FRESHNESS_WINDOW_SEC, MIT_HOLD_KD, MIT_HOLD_KP
from backend.actuation.safety import KD_MAX, KD_MIN
from backend.dynamics.constants import ARM_JOINT_COUNT
from contracts.units import Nm, RadPerSec

__all__ = [
    "ARM_JOINT_COUNT",
    "DEFAULT_EFFORT_HEADROOM",
    "DEFAULT_KD_FREEDRIVE",
    "FREEDRIVE_CONTROL_PERIOD_SEC",
    "FREEDRIVE_DQ",
    "FREEDRIVE_FIXTURE_ENV_VAR",
    "FREEDRIVE_FRESHNESS_WINDOW_SEC",
    "FREEDRIVE_KP",
    "FREEDRIVE_PRODUCER_ID",
    "FREEDRIVE_TAU_FLOOR_NM",
    "FRICTION_PASSED_STATUS",
    "GRAVITY_UNCOMPENSATED_BANNER",
    "HOLD_RESTORE_KD",
    "HOLD_RESTORE_KP",
    "KD_FREEDRIVE_SUGGESTED_MAX",
    "KD_FREEDRIVE_SUGGESTED_MIN",
    "KD_MAX",
    "KD_MIN",
]

# Path (C) stiffness: zero. Damiao's MIT law with kp=0 lets a commanded t_ff become a pure
# torque output (spec 04 §2.8), which is what makes the joint back-drivable under gravity
# compensation rather than servoing to a held angle.
FREEDRIVE_KP = 0.0

# Path (C) damping default and the spec's suggested band (FR-MAN-030: "0.1-0.3, per-joint
# settable"). It is a small oscillation-suppression term, not a position gain; the value is
# validated against the MIT kd band [KD_MIN, KD_MAX] before it can be commanded.
DEFAULT_KD_FREEDRIVE = 0.2
KD_FREEDRIVE_SUGGESTED_MIN = 0.1
KD_FREEDRIVE_SUGGESTED_MAX = 0.3

# The commanded velocity of a Freedrive frame is zero: path (C) is a position-less torque
# feed-forward, so dq carries no motion of its own (spec 04 §2.8, FR-MAN-030).
FREEDRIVE_DQ = RadPerSec(0.0)

# The position-hold gains a Freedrive exit restores to. The exit re-commands position with the
# hold kd BEFORE (in the same MIT frame as) the hold kp, so the forbidden (kp>0, kd=0) state a
# Damiao motor vibrates on (spec 04 §2.4) never exists on the wire. These mirror the actuation
# hold gains so the Cat-2 hold a Freedrive exit produces is the same hold the scheduler caches.
HOLD_RESTORE_KP = MIT_HOLD_KP
HOLD_RESTORE_KD = MIT_HOLD_KD

# Fraction of a joint's peak torque the gravity term must stay under to admit Freedrive entry
# (acceptance IV). Entry is refused if gravity alone already needs >= this fraction of the
# actuator's effort, because compensation would then have no headroom left for the friction
# term and the damping the hand-guide adds. This is a Freedrive entry-margin policy, not a
# motor rating: the rating is the peak torque the SafetyLimits carries.
DEFAULT_EFFORT_HEADROOM = 0.9

# Torque magnitudes at or below this (Nm) are treated as zero when deciding whether the gateway
# clamped a Freedrive torque. It absorbs the deg->rad round trip through the gateway so a
# clamp verdict reflects a real peak-torque cut, not floating-point noise.
FREEDRIVE_TAU_FLOOR_NM = Nm(1.0e-6)

# The gateway's control period and freshness window for the Freedrive command path. The period
# feeds the rate checks; a Freedrive frame is a zero-delta command, so the value only sets the
# denominator of checks a held-position command passes trivially. Freshness is reused from the
# actuation spine so a stalled Freedrive producer is stale on the same horizon as any producer.
FREEDRIVE_CONTROL_PERIOD_SEC = 0.02
FREEDRIVE_FRESHNESS_WINDOW_SEC = FRESHNESS_WINDOW_SEC

# The scheduler-producer identity Freedrive publishes under, for swap accounting and the trace.
FREEDRIVE_PRODUCER_ID = "freedrive"

# The banner FR-MAN-035 requires whenever path (C) is unavailable: Freedrive is then offered
# only as (A)/(B), which do not compensate gravity, so the arm sags. The text is the operator's
# Korean UI string, shown for the same readers as docs/spec.
GRAVITY_UNCOMPENSATED_BANNER = "중력 미보상 — 팔이 처짐"

# The friction-gate marker that opens path (C). Only a real PG-FRIC-001 hardware pass (real
# excitation logs plus a PG-J7-001 torque-scale pass) may set it, which is why the friction
# writer cannot emit it and this host — running on synthetic logs — never sees it. The gate maps
# every other status, including the synthetic-log NOT_PASSED_DEFERRED_TO_HARDWARE, to blocked.
FRICTION_PASSED_STATUS = "PG_FRIC_001_PASS"

# Environment variable naming the directory of real Freedrive registration captures the deferred
# re-verification hook re-runs the identical offline checks against, once hardware exists.
FREEDRIVE_FIXTURE_ENV_VAR = "OPENARM_FREEDRIVE_REAL_FIXTURE"
