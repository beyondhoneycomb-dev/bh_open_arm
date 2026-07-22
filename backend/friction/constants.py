"""Domain constants for the WP-2B-07 friction least-squares identification (PG-FRIC-001).

The friction model is the four-term tanh law spec 04 FR-MAN-034 fixes:
`tau_fric(omega) = Fo + Fv*omega + Fc*tanh(k_eff*omega)`. The one constant that is a genuine
trap rather than a value is `K_EFF_SCALE`: the runtime (`control.cpp::ComputeFriction`,
`coef_tmp = 0.1`) applies `k_eff = 0.1 * k`, so the `k` written in the YAML is a tenth of the
tanh slope it names. Every consumer of this package must carry that convention, so it lives
here once and the writer stamps it into every file's metadata (acceptance ②).
"""

from __future__ import annotations

from backend.dynamics.constants import ARM_JOINT_COUNT

__all__ = [
    "ARM_JOINT_COUNT",
    "BASIS_SYNTHETIC_LOG",
    "FIXTURE_ENV_VAR",
    "FRICTION_YAML_FILENAME",
    "IDENTIFIED_ROBOT_VERSION",
    "K_EFF_SCALE",
    "KNEE_RESOLUTION_AT_REFERENCE_RAD_S",
    "LOG_FREQ_REFERENCE_HZ",
    "PARAM_KEY_FC",
    "PARAM_KEY_FO",
    "PARAM_KEY_FV",
    "PARAM_KEY_K",
    "PG_FRIC_001_STATUS_DEFERRED",
    "SEPARATION_MAX_ABS_CORR",
    "SEPARATION_MIN_R2",
    "SYNTHETIC_LOG_SEED",
]

# k_eff = K_EFF_SCALE * k. Spec 04 FR-MAN-034: the documented formula writes `tanh(k*omega)`
# but the code path multiplies k by 0.1 (`control.cpp` `coef_tmp = 0.1`), so a fit that
# recovers the true tanh slope `k_eff` must store `k = k_eff / K_EFF_SCALE` for the runtime to
# reconstruct it. Writing the raw slope as `k` would make the deployed friction ten times too
# soft in the stiction knee.
K_EFF_SCALE = 0.1

# YAML parameter key names. These match the enactic `friction.yaml` schema
# (`comp.friction_Fc/k/Fv/Fo`) so an identified file drops into the same slot the empty
# upstream file occupies; the Python attributes are snake_case (`f_o`/`f_v`/`f_c`/`k_eff`).
PARAM_KEY_FO = "Fo"
PARAM_KEY_FV = "Fv"
PARAM_KEY_FC = "Fc"
PARAM_KEY_K = "k"

# The canonical logging rate friction identification is specified against (spec 12 §2.6 path A,
# "1 kHz pos/vel/tau logging"). WP-2B-05 ties the achieved rate to the scheduler tick, so the
# real rate can be lower; the identification band is recorded as a function of it (acceptance
# ③), and a lower rate shrinks the band from the low-velocity (stiction) end first (§2.1).
LOG_FREQ_REFERENCE_HZ = 1000.0

# The lowest velocity whose friction is resolvable at the reference logging rate, rad/s. The
# tanh knee sits near omega = 1/k_eff; resolving it needs enough low-velocity samples, and that
# sample density scales with the logging rate. The band's lower edge is modelled as
# `omega_lo(f) = KNEE_RESOLUTION_AT_REFERENCE_RAD_S * (LOG_FREQ_REFERENCE_HZ / f)`, so halving
# the rate doubles the smallest resolvable velocity and eats into the stiction knee first
# (§2.1). This is a modelling assumption of the identification band, not a measured figure.
KNEE_RESOLUTION_AT_REFERENCE_RAD_S = 0.01

# Separation acceptance thresholds (acceptance ①). After the friction fit is subtracted, the
# post-fit residual must not still be explained by the gravity, Coriolis or inertia signal — a
# lingering correlation is the fingerprint of a friction fit absorbing a model error (§2.0). A
# fit is `separated` when every |correlation| with a model signal is below the first threshold
# and the fit explains at least the second fraction of the friction-band variance.
SEPARATION_MAX_ABS_CORR = 0.2
SEPARATION_MIN_R2 = 0.9

# The robot generation identified friction parameters describe. The stamp is 2.0 because the
# fit targets the v2 arm; the provisional/synthetic status is carried separately in the file's
# `status` block, never by pretending the parameters are for a different robot.
IDENTIFIED_ROBOT_VERSION = "2.0"

# The friction-fit basis marker written into a synthetic-log file's status block. A real
# PG-FRIC-001 pass replaces it with a real-excitation-log basis; this value is the honest
# record that the numbers came from a synthetic log and are not a hardware pass (THE ONE RULE).
BASIS_SYNTHETIC_LOG = "SYNTHETIC_EXCITATION_LOG"

# The PG-FRIC-001 gate status a synthetic-log fit is allowed to claim: not passed, deferred to
# hardware. A synthetic-log fit proves the identification math converges and separates; it can
# never be a PG-FRIC-001 pass, which needs real excitation logs (WP-2B-06 on hardware) and a
# PG-J7-001 torque-scale pass. The writer refuses to stamp any stronger status on this basis.
PG_FRIC_001_STATUS_DEFERRED = "NOT_PASSED_DEFERRED_TO_HARDWARE"

# Environment variable naming the directory of real excitation captures the re-verification
# hook re-runs the identical fit against, once WP-2B-06 has produced them on hardware.
FIXTURE_ENV_VAR = "OPENARM_FRICTION_REAL_FIXTURE"

# Default filename for a written friction table. `.provisional.` is part of the name so a file
# produced from a synthetic log can never be mistaken on disk for a validated v2 asset.
FRICTION_YAML_FILENAME = "friction.provisional.yaml"

# Deterministic seed for the synthetic excitation-log generator, so the demonstration file and
# the drift-guard test regenerate byte-for-byte on a fixed numpy/scipy.
SYNTHETIC_LOG_SEED = 20260722
