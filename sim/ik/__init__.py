"""IK adapter over the fixed MJCF asset (WP-0C-02).

The single sanctioned way to reach a ``Kinematics`` for this platform: the jnt_range
override runs first (09 FR-SIM-080), the unconstrained fallback is off by default
(12 FR-SAF-016), and every solve reports the four FR-OPS-043 failure conditions as
distinct ``OA-IK-*`` codes. Consumers import the ordered builder and the adapter from
here — never ``openarm_control``'s ``Kinematics`` directly, which
``sim.ik.staticcheck`` enforces.
"""

from sim.ik.adapter import IkAdapter, IkOutcome, build_ik_adapter
from sim.ik.faults import FaultReporter, IkFault, IkFaultCode
from sim.ik.limits import JointLimit, all_soft_limits, arm_soft_limits, soft_limits
from sim.ik.override import (
    BuildStage,
    IkOrderError,
    LimitMismatchError,
    OrderedIkBuild,
    overwrite_jnt_range,
    verify_ranges_match,
)

__all__ = [
    "BuildStage",
    "FaultReporter",
    "IkAdapter",
    "IkFault",
    "IkFaultCode",
    "IkOrderError",
    "IkOutcome",
    "JointLimit",
    "LimitMismatchError",
    "OrderedIkBuild",
    "all_soft_limits",
    "arm_soft_limits",
    "build_ik_adapter",
    "overwrite_jnt_range",
    "soft_limits",
    "verify_ranges_match",
]
