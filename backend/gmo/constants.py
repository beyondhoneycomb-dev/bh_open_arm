"""Domain constants for the WP-2C-01 generalized-momentum observer (GMO).

The observer's model terms are not defined here — they are reused: gravity and Coriolis from
`backend.gravity` (WP-2B-02) and friction from `backend.friction` (WP-2B-07). This module holds
only the observer's own tuning scalars and the arm width it operates on.

Two numbers are deliberately nominal, not calibrated, because their canonical values are
hardware-measured and this host has no arm:

  * `DEFAULT_OBSERVER_GAIN` is the residual-loop bandwidth `K`. NFR-SAF-002 anchors the reaction
    time to `~1/K` with a reference `K = 90`, so 90 is the per-joint default; the per-joint tuned
    set is a torque-ON measurement (WP-2C-06) and is deferred.
  * `NOMINAL_DETECTION_DT_S` is the 1 kHz nominal detection period. The achieved cycle time is
    measured on hardware (WP-2C-02) and may clamp to <=625 Hz under pattern B (NFR-SAF-001); this
    scalar is the offline default, not a claim about the real loop rate.

The per-joint detection *thresholds* live nowhere in this package on purpose: they are WP-2C-03's
calibrated output, so the isolation surface here takes them as an argument rather than baking a
number a torque-ON wizard is meant to own.
"""

from __future__ import annotations

from backend.dynamics.constants import ARM_JOINT_COUNT

# The observer operates on one arm's seven actuated joints. The gripper (J8) carries no residual
# term here: WP-2C-11 keeps gripper residual detection disabled (no finger-dynamics model, grasp
# reaction is a standing offset), so it is not this observer's concern.
GMO_JOINT_COUNT = ARM_JOINT_COUNT

# Residual-loop bandwidth default, s^-1. r tracks the external torque with first-order dynamics
# `r_dot = K*(tau_ext - r)`, so a larger K reacts faster and passes more model noise. 90 is the
# NFR-SAF-002 reference; the per-joint tuned vector is deferred (WP-2C-06, torque-ON).
DEFAULT_OBSERVER_GAIN = 90.0

# A residual-loop gain must be strictly positive: `r_dot = K*(tau_ext - r)` is only a stable
# low-pass toward `tau_ext` for `K > 0`. A non-positive gain is a configuration error, refused
# rather than run into an unstable or frozen observer.
OBSERVER_GAIN_MIN = 0.0

# Nominal detection-loop period, s (1 kHz). The achieved rate is a hardware measurement (WP-2C-02)
# and may be clamped lower; this is the offline default the synthetic harness integrates at.
NOMINAL_DETECTION_DT_S = 1.0e-3
