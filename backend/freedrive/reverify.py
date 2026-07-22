"""Real-fixture re-verification hook for the deferred Freedrive registration (THE ONE RULE).

Phase 1 of this WP is AI-offline: the path-(C) command, the entry gates, and the exit order all
run and are checked here on synthetic poses. Phase 2 — real Freedrive registration — is
Human-assisted-HW: it needs a real PG-FRIC-001 pass (real friction) and torque-ON on a brakeless
arm, of which this host has neither. That acceptance is skipped with a reason, never asserted
green.

This is the hook the deferral ships. The moment a directory of real registration captures is
supplied via ``OPENARM_FREEDRIVE_REAL_FIXTURE``, ``reverify_freedrive_registration`` re-runs the
*identical* entry decision — the same friction gate, the same effort-saturation check, the same
producer — over the real poses and reports what each would do. It renders no pass on its own: the
friction-pass and torque-ON preconditions are hardware gates the hook cannot evaluate, so it
reports the evidence and leaves the pass decision to the acceptance runner that also checks them.
The hook can never manufacture a green the offline path would not, because it is the offline path
pointed at real data.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.actuation.clock import ManualClock
from backend.actuation.safety import SafetyLimits
from backend.freedrive.constants import FREEDRIVE_FIXTURE_ENV_VAR
from backend.freedrive.gate import FrictionGate, friction_gate_status
from backend.freedrive.session import FreedriveSession
from backend.friction.model import FrictionParams
from backend.gravity.backend import GravityBackend

# The external gates a real registration still requires; carried on every evidence record as a
# constant reminder that this hook's output is not a pass without them.
_TORQUE_ON_PRECONDITION = "torque-ON on a brakeless arm required; not evaluated by this hook"
_FRICTION_PASS_PRECONDITION = (
    "PG-FRIC-001 PASS required; the captured friction status is read, never assumed"
)


@dataclass(frozen=True)
class FreedriveRegistrationEvidence:
    """What re-running the identical entry decision over one real capture produced.

    Attributes:
        capture_id: The capture's identifier (its filename stem by default).
        friction_status: The friction status the capture recorded.
        path_c_offered: Whether the friction gate offered path (C) for that status.
        effort_saturated: Whether gravity torque saturated the effort at the captured pose.
        engaged: Whether the entry decision engaged Freedrive on the real pose.
        min_hold_kd: The smallest damping the exit hold restored, evidence that no kd=0 position
            hold is produced even on real data.
        torque_on_precondition: The hardware gate a real pass still requires.
        friction_pass_precondition: The friction gate a real pass still requires.
    """

    capture_id: str
    friction_status: str
    path_c_offered: bool
    effort_saturated: bool
    engaged: bool
    min_hold_kd: float
    torque_on_precondition: str
    friction_pass_precondition: str


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(FREEDRIVE_FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _verify_one(
    capture_id: str,
    capture: dict[str, Any],
    gravity_backend: GravityBackend,
    friction_params: tuple[FrictionParams, ...],
    safety_limits: SafetyLimits,
) -> FreedriveRegistrationEvidence:
    """Re-run the identical entry decision and exit over one real capture.

    Args:
        capture_id: The capture identifier.
        capture: A parsed capture with ``q``, ``dq`` and ``friction_status``.
        gravity_backend: The single gravity source.
        friction_params: Per-joint identified friction law.
        safety_limits: The clamp envelope the gateway and effort check share.

    Returns:
        (FreedriveRegistrationEvidence) The evidence the real pose produced.

    Raises:
        KeyError: If the capture is missing a required channel.
    """
    q_entry = tuple(float(value) for value in capture["q"])
    dq_entry = tuple(float(value) for value in capture["dq"])
    friction_status = str(capture["friction_status"])

    clock = ManualClock()
    gate = FrictionGate(friction_gate_status(friction_status))
    session = FreedriveSession(
        gravity_backend=gravity_backend,
        friction_params=friction_params,
        safety_limits=safety_limits,
        gate=gate,
        clock=clock,
    )
    session.hold_heartbeat()
    entry = session.enter(q_entry, dq_entry)
    exit_hold = session.release(q_entry)

    return FreedriveRegistrationEvidence(
        capture_id=capture_id,
        friction_status=friction_status,
        path_c_offered=gate.path_c_available,
        effort_saturated=entry.effort.saturated if entry.effort is not None else False,
        engaged=entry.engaged,
        min_hold_kd=min(exit_hold.restored_kd),
        torque_on_precondition=_TORQUE_ON_PRECONDITION,
        friction_pass_precondition=_FRICTION_PASS_PRECONDITION,
    )


def reverify_freedrive_registration(
    fixture_dir: Path,
    gravity_backend: GravityBackend,
    friction_params: tuple[FrictionParams, ...],
    safety_limits: SafetyLimits,
) -> list[FreedriveRegistrationEvidence]:
    """Re-run the Freedrive entry decision against real registration captures.

    Loads every ``*.json`` capture in the directory and runs the identical entry decision and
    exit the offline demonstration exercises, now pointed at real poses. This is the
    re-verification the deferred hardware acceptance requires; it renders evidence, not a pass.

    Args:
        fixture_dir: Directory of captured registration JSON files, one per session.
        gravity_backend: The single gravity source.
        friction_params: Per-joint identified friction law.
        safety_limits: The clamp envelope the gateway and effort check share.

    Returns:
        (list[FreedriveRegistrationEvidence]) One evidence record per capture, ordered by name.

    Raises:
        FileNotFoundError: If the directory holds no ``*.json`` capture.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json freedrive capture in {fixture_dir}")
    return [
        _verify_one(
            path.stem,
            json.loads(path.read_text(encoding="utf-8")),
            gravity_backend,
            friction_params,
            safety_limits,
        )
        for path in capture_files
    ]
