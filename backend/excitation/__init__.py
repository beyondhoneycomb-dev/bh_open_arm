"""WP-2B-06 — exciting-trajectory design and the injection harness (FR-SAF-029, FR-MAN-035).

The identification excitation for the friction fit (`WP-2B-07`), split into the part that
runs `AI-offline` on this host and the part that is torque-ON and deferred:

* `design_band` derives the identification band from the achieved logging frequency
  (`02b` §2.1): its ceiling tracks the tick rate and its stiction-knee flag records
  whether the rate is high enough to resolve the low-speed `tanh` region.
* `ExcitingTrajectory` is the per-joint Schroeder-phased multisine over that band,
  addressable by index and refusing any spec that would leave a joint's bounds.
* `AbortMonitor` is the four-cause abort detector (ERR nibble, comm loss, over-temp,
  joint limit, human abort), reusing the `backend.commloss` watchdog and the shared
  one-way `SafetyLatch` so every cause ends in one operator-cleared hold.
* `ExcitationInjector` enforces the three hard gates — an `FR-MOT-058` torque path, an
  armed `WP-2A-00` dry-run barrier, and a confirmed safe initial state — then drives the
  trajectory, stops on the first abort, records the resume index, and continues from it.
* `reverify_injection_sessions` is the re-verification hook for the deferred on-arm run;
  the actual injection is SKIPPED WITH A REASON, never asserted (a faked injection green
  is a safety lie).
"""

from __future__ import annotations

from backend.excitation.abort import (
    AbortCause,
    AbortDecision,
    AbortMonitor,
    TickObservation,
)
from backend.excitation.band import ExcitationBand, design_band
from backend.excitation.constants import (
    DEFAULT_MAX_MOTOR_TEMP_C,
    NOMINAL_LOGGING_HZ,
    REPEATED_HUMAN_ABORT_LIMIT,
    STICTION_KNEE_MIN_LOGGING_HZ,
)
from backend.excitation.errors import (
    DryRunGateNotArmedError,
    ExcitationError,
    LatchStillEngagedError,
    TorquePathUnavailableError,
    TrajectoryLimitError,
    UnsafeInitialStateError,
)
from backend.excitation.injection import (
    ExcitationInjector,
    InjectionResult,
    InjectionStatus,
    Observer,
    SafeInitialState,
)
from backend.excitation.reverify import (
    FIXTURE_ENV_VAR,
    ReverifyResult,
    fixture_dir_from_env,
    reverify_injection_sessions,
)
from backend.excitation.torque_path import (
    TorqueCommand,
    TorqueCommandPath,
    torque_widths_match,
)
from backend.excitation.trajectory import (
    ExcitingTrajectory,
    JointBounds,
    JointExcitation,
    TrajectorySample,
)

__all__ = [
    "DEFAULT_MAX_MOTOR_TEMP_C",
    "FIXTURE_ENV_VAR",
    "NOMINAL_LOGGING_HZ",
    "REPEATED_HUMAN_ABORT_LIMIT",
    "STICTION_KNEE_MIN_LOGGING_HZ",
    "AbortCause",
    "AbortDecision",
    "AbortMonitor",
    "DryRunGateNotArmedError",
    "ExcitationBand",
    "ExcitationError",
    "ExcitationInjector",
    "ExcitingTrajectory",
    "InjectionResult",
    "InjectionStatus",
    "JointBounds",
    "JointExcitation",
    "LatchStillEngagedError",
    "Observer",
    "ReverifyResult",
    "SafeInitialState",
    "TickObservation",
    "TorqueCommand",
    "TorqueCommandPath",
    "TorquePathUnavailableError",
    "TrajectoryLimitError",
    "TrajectorySample",
    "UnsafeInitialStateError",
    "design_band",
    "fixture_dir_from_env",
    "reverify_injection_sessions",
    "torque_widths_match",
]
