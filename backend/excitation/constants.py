"""Named parameters of the WP-2B-06 exciting-trajectory design and injection harness.

Every literal the band design, the abort logic, and the injection preconditions
depend on is named here, so the one place a threshold is decided is the one place it
is read (`14` §2, constants rule). The band numbers encode `02b` §2.1's honest
consequence directly: the identification band's upper edge is a function of the
achieved logging frequency, and the low-speed stiction knee (`tanh` region) is the
first thing lost when that frequency falls below 1 kHz.
"""

from __future__ import annotations

# The nominal `02b` §2.1 logging/tick rate the whole band was sized against. A real
# run reports its achieved rate (`WP-2B-05`) and the band is re-derived from it.
NOMINAL_LOGGING_HZ = 1000.0

# Minimum samples per cycle at the band's upper edge, so the band ceiling is
# `f_log / MIN_SAMPLES_PER_CYCLE`. The stiction knee is a sub-cycle feature — it
# occupies the brief interval each period when velocity crosses zero — so resolving
# it needs many samples within the highest tone's own cycle, not merely two. A
# hundred keeps that ceiling well under the achieved rate and makes the band a real
# function of `f_log`: at 1 kHz the ceiling is 10 Hz, at 625 Hz it falls to 6.25 Hz.
MIN_SAMPLES_PER_CYCLE = 100.0

# A physical ceiling on excitation frequency independent of logging: past this the
# joint's own mechanical bandwidth attenuates the command, so a higher `f_log` buys
# no more identifiable content. The band ceiling is the smaller of this and the
# sampling-derived limit, so it only caps runs whose logging rate exceeds ~1.2 kHz.
IDENT_FREQ_CAP_HZ = 12.0

# The band's fixed lower edge: a slow zero-crossing sweep that carries the joint
# velocity through the low-speed stiction region so the `tanh` knee (`F_c`) is
# excited at all. 0.1 Hz is a ten-second period. Unlike the ceiling, the floor does
# not move with `f_log`; what `f_log` decides is whether that knee is *resolved*.
STICTION_SWEEP_HZ = 0.1

# Below this achieved logging frequency the low-speed stiction knee is under-sampled
# and cannot be trusted — `02b` §2.1: the `tanh` knee is the first casualty of a
# logging downgrade. A band derived from a slower rate is still valid for the viscous
# and Coulomb terms but is flagged as not resolving the knee, so `PG-FRIC-001` can
# only reach `DEGRADED_ACCEPTED` on it (never a clean stiction pass).
STICTION_KNEE_MIN_LOGGING_HZ = 1000.0

# Default number of harmonically spaced sinusoids in a per-joint multisine. Enough
# to spread energy across the band for a well-conditioned fit without a crest factor
# that spikes the commanded torque.
DEFAULT_HARMONIC_COUNT = 8

# Over-temperature abort ceiling for a Damiao motor's reported temperature, °C. A
# reading at or above this stops injection immediately (`02b` §2.3 ②, abort on temp).
DEFAULT_MAX_MOTOR_TEMP_C = 80.0

# Repeated human aborts of the same session mean the rig itself is wrong, not the
# trajectory. At this count the session surfaces `FAIL_BLOCKING` — `02b` §2.3 negative
# branch: repeated human abort forces a rig re-review rather than another retry.
REPEATED_HUMAN_ABORT_LIMIT = 3

# The `LatchReason.gate_id` prefix an excitation abort stamps, so an audited hold is
# attributable to this harness rather than to the comm-loss watchdog or another
# latch source. The ERR-nibble and comm-loss causes keep the watchdog's own prefix,
# since those latches are engaged by the reused `backend.commloss` watchdog.
ABORT_GATE_PREFIX = "EXCITATION_ABORT"
