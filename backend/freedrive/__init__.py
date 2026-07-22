"""WP-2D-03 — gravity-compensated Freedrive (path C), the hand-guiding command path.

Freedrive path (C) commands ``(kp=0, kd=kd_freedrive, q, dq=0, tau=tau_grav(q)+tau_fric(dq))``
per joint (spec 04 FR-MAN-030). This package builds that command as a scheduler producer over the
reused spine, and the mode around it:

* ``FreedriveProducer`` — the path-(C) command, routed through the single enforcement gateway
  (I-4). It releases the position path's tau-zero constraint through the sanctioned torque
  channel while reaching no CAN handle of its own.
* ``FrictionGate`` / ``friction_gate_status`` — path (C) is offered only on a PG-FRIC-001 pass;
  otherwise Freedrive is (A)/(B) with the FR-MAN-035 "gravity uncompensated - arm sags" banner.
* ``EffortSaturationCheck`` — entry is refused when gravity torque saturates the effort at the
  pose, so compensation is never promised where the actuator has no headroom for it.
* ``FreedriveSession`` — deadman hold-to-activate (reused ``backend.deadman``), immediate Cat-2
  hold on release, and the kd-restore-before-position exit order (no kd=0 position command).
* ``reverify_freedrive_registration`` — the deferred real-registration hook (needs PG-FRIC-001
  and torque-ON), which re-runs the identical entry decision on real captures but renders no pass.

What runs here (AI-offline, synthetic poses) and what is deferred (a real registration on
hardware) are kept strictly apart: the offline path never asserts the hardware pass it cannot see.
"""

from __future__ import annotations

from backend.freedrive.constants import (
    DEFAULT_KD_FREEDRIVE,
    FREEDRIVE_FIXTURE_ENV_VAR,
    FREEDRIVE_KP,
    FRICTION_PASSED_STATUS,
    GRAVITY_UNCOMPENSATED_BANNER,
)
from backend.freedrive.effort import EffortSaturation, EffortSaturationCheck
from backend.freedrive.gate import (
    FreedrivePath,
    FrictionGate,
    FrictionGateStatus,
    friction_gate_status,
)
from backend.freedrive.producer import FreedriveFrame, FreedriveProducer
from backend.freedrive.reverify import (
    FreedriveRegistrationEvidence,
    fixture_dir_from_env,
    reverify_freedrive_registration,
)
from backend.freedrive.session import (
    EntryRefusal,
    ExitToHold,
    FreedriveEntry,
    FreedriveSession,
    FreedriveTick,
    HoldCause,
    TickMode,
)
from backend.freedrive.staticcheck import (
    find_toggle_or_autohold,
    references_single_gateway,
    scan_freedrive_single_gateway,
)

__all__ = [
    "DEFAULT_KD_FREEDRIVE",
    "FREEDRIVE_FIXTURE_ENV_VAR",
    "FREEDRIVE_KP",
    "FRICTION_PASSED_STATUS",
    "GRAVITY_UNCOMPENSATED_BANNER",
    "EffortSaturation",
    "EffortSaturationCheck",
    "EntryRefusal",
    "ExitToHold",
    "FreedriveEntry",
    "FreedriveFrame",
    "FreedrivePath",
    "FreedriveProducer",
    "FreedriveRegistrationEvidence",
    "FreedriveSession",
    "FreedriveTick",
    "FrictionGate",
    "FrictionGateStatus",
    "HoldCause",
    "TickMode",
    "find_toggle_or_autohold",
    "fixture_dir_from_env",
    "friction_gate_status",
    "references_single_gateway",
    "reverify_freedrive_registration",
    "scan_freedrive_single_gateway",
]
