"""Domain constants for the WP-2B-09 detection/control compensation-scale separation.

The core invariant this package defends (FR-SAF-035, spec 12 §2.6): the collision-residual
observer (WP-2C-01) and the control feedforward apply compensation on two *independent* scale
sets, and the two must never collapse into one variable.

* The detection model runs at **100%** — the residual `r = tau_meas - model(q, q̇)` is only an
  estimate of external torque when the model it subtracts is the full modelled dynamics. A
  detection model scaled below 100% leaves the un-modelled fraction of friction/Coriolis in the
  residual as a standing offset, which then sets the collision threshold floor and either
  masks real contact or fires on none.
* The control feedforward runs at a **partial** scale — friction `0.3`, Coriolis `0.1`. These
  are provisional v1 partial-compensation coefficients carried over from the v1 `openarm_teleop`
  follower lineage, NOT values identified by a real `PG-FRIC-001` friction fit (WP-2B-07 is the
  package that produces those, and it is hardware-gated). They stay conservative on purpose:
  over-compensating a provisional friction estimate injects energy and can destabilise the arm.

Because the two live on separate axes, the failure mode is exactly "bind them to one knob": the
control coefficient `0.3` would become the detection model's friction scale, and the 70% it
does not compensate would land in the residual as a constant error dominating the threshold.
"""

from __future__ import annotations

# The detection (residual-observer) model scale. Fixed at 1.0: the residual subtracts the FULL
# modelled dynamics, so any other value is a misconfiguration, not a tuning knob (FR-SAF-035).
DETECTION_MODEL_SCALE = 1.0

# Control-feedforward partial-compensation coefficients. Provisional v1 values (see module
# docstring): friction 0.3, Coriolis 0.1. Not a real PG-FRIC-001 fit — treat as provisional
# until WP-2B-07 identifies friction on hardware.
FRICTION_COMP_SCALE_DEFAULT = 0.3
CORIOLIS_COMP_SCALE_DEFAULT = 0.1

# A compensation scale is a fraction of the modelled term to feed forward: 0 = no compensation,
# 1 = full. A value above 1 over-compensates (energy injection); below 0 is nonsense. Both are
# refused at construction rather than silently clamped.
COMP_SCALE_MIN = 0.0
COMP_SCALE_MAX = 1.0
