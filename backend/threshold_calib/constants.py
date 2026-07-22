"""Named constants for the collision-threshold calibration wizard (WP-2C-03).

Nothing here re-declares a physics-owned quantity. The ten-LSB floor, the URDF effort
cap, the seven-joint motor map, the +-10%-of-effort default and its provenance label are
owned by WP-1-06 and imported from `backend.safety_bringup`; re-typing any of them would
create the second source of truth the audit hunts for (`12` FR-SAF-019/020). What lives
here is only the calibration *proposal rule* — the `max + 3sigma` and nominal-scaled
statistics of `12` FR-SAF-060 — the `12` FR-SAF-063 sensitivity-preset bundles, and the
deferred-run hook's environment variable.

The proposal figures are literature-rule tuning parameters (PMC7805958, `12` §2.5), not
OpenArm-measured values: the wizard's *output* becomes canon only after a real
collision-free run under an operator's no-collision judgment (`wizard`, `reverify`).
"""

from __future__ import annotations

from dataclasses import dataclass

# The `max + 3sigma` rule of `12` FR-SAF-060: a per-joint threshold is the collision-free
# residual's maximum magnitude plus three standard deviations, so a no-collision run stays
# under it with high probability. The multiple is the literature tuning figure, not a
# measured OpenArm quantity.
SIGMA_MULTIPLE = 3.0

# The nominal-scaled rule of `12` FR-SAF-060: a per-joint threshold is 105-110 % of the
# collision-free residual's maximum magnitude. The margin is bounded so a caller cannot
# scale a threshold arbitrarily far from the observed no-collision envelope; the default is
# the widest admitted margin, the most tolerant of residual variation between runs.
NOMINAL_SCALE_MIN = 1.05
NOMINAL_SCALE_MAX = 1.10
NOMINAL_SCALE_DEFAULT = 1.10

# A standard deviation from one sample is undefined and a maximum from a single run is not
# an envelope, so a proposal is refused below these counts rather than emitting a threshold
# a reader would mistake for calibrated (`12` FR-SAF-060 repeated-run rule, acceptance 1).
MIN_RUNS_FOR_PROPOSAL = 2
MIN_SAMPLES_FOR_PROPOSAL = 2

# The two proposal methods `12` FR-SAF-060 names. Stored as identifiers so a proposal
# records which rule produced it and the display can label the two differently.
METHOD_MAX_PLUS_SIGMA = "max_plus_3sigma"
METHOD_NOMINAL_SCALED = "nominal_scaled"

# The `12` FR-SAF-063 sensitivity presets. Each bundles a threshold scale applied to the
# calibrated base, an observer gain, and a confirm-sample count, so one control moves all
# three together. HIGH sensitivity lowers the threshold and the confirm count (trips
# sooner); LOW raises them (trips less). The confirm-sample logic itself is WP-2C-04's
# frozen contract — this bundle carries only the *value* the preset selects, not the
# debounce implementation. The gain figure follows the v1 observer cutoff (`12` §2.12 Q6,
# K=90 at MEDIUM); every figure here is a design default, not an OpenArm-measured value.
CONFIRM_SAMPLES_DEFAULT = 5
OBSERVER_GAIN_DEFAULT = 90.0


@dataclass(frozen=True)
class SensitivityPreset:
    """One `12` FR-SAF-063 sensitivity preset and the three values it bundles.

    Attributes:
        name: The preset identifier (`LOW`/`MEDIUM`/`HIGH`).
        threshold_scale: Multiplier on the calibrated base threshold; <1 raises sensitivity.
        observer_gain: The GMO observer gain K the preset selects.
        confirm_samples: The consecutive-over-threshold count the preset selects; the
            debounce that consumes it is WP-2C-04's, not this package's.
    """

    name: str
    threshold_scale: float
    observer_gain: float
    confirm_samples: int


SENSITIVITY_LOW = "LOW"
SENSITIVITY_MEDIUM = "MEDIUM"
SENSITIVITY_HIGH = "HIGH"

SENSITIVITY_PRESETS: dict[str, SensitivityPreset] = {
    SENSITIVITY_LOW: SensitivityPreset(SENSITIVITY_LOW, 1.30, 60.0, 8),
    SENSITIVITY_MEDIUM: SensitivityPreset(SENSITIVITY_MEDIUM, 1.00, OBSERVER_GAIN_DEFAULT, 5),
    SENSITIVITY_HIGH: SensitivityPreset(SENSITIVITY_HIGH, 0.80, 120.0, 3),
}

# Provenance labels the wizard stamps onto a proposal. A calibration derived from a
# synthetic residual stream is a demonstration of the math, never a measured threshold, and
# must say so; only an operator-attested real run earns the canon label. THE ONE RULE: the
# offline path can never present the synthetic label as the attested one.
PROVENANCE_SYNTHETIC = (
    "synthetic residual stream (offline demonstration of the calibration math); "
    "NOT an OpenArm-measured threshold"
)
PROVENANCE_REAL_ATTESTED = (
    "real collision-free residual run, operator-attested no-collision (12 FR-SAF-060)"
)

# Environment variable naming a directory of real collision-free residual captures for the
# deferred calibration run (`02a` §4.1 re-verification hook). Until it is set, the real-run
# acceptance skips with a reason and is never asserted green: the run needs a powered arm,
# WP-2C-01's live residual, and an operator watching for contact, none of which exist on a
# desktop host.
FIXTURE_ENV_VAR = "OPENARM_THRESHOLD_CALIB_REAL_FIXTURE"
