"""Real-fixture re-verification for the deferred live payload registration (WP-2B-04 phase 2).

The model math runs on this host: registering a payload reflects into `tau_grav`, the effort
preflight refuses a saturating pose, and the residual check shows a registered payload change
does not read as a collision. What does not run here is *live* registration verification —
mounting a real payload, holding it torque-ON, and confirming the registered mass/CoG matches
the measured static-hold torque. That needs the powered brakeless arm and a torque-ON hold,
which this host has no CAN, no motor, and no PG-SAFE-001 PASS for. It is deferred — skipped
with a reason, never asserted green.

This is the hook the deferral ships. Given a directory of real static-hold captures (pose,
measured joint torque, the declared registered payload), `reverify_from_fixture` re-runs the
*identical* residual check the offline acceptance runs, now against the measured torque, and
confirms a registration only when the residual falls below the collision threshold on every
joint. A capture whose measured hold disagrees with the declared payload is reported as
NOT confirmed, so the hook can never manufacture a registration pass THE ONE RULE forbids:
the residual basis is the measurement, and the model it is compared against is the declared
payload — the check cannot approve itself.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.gravity import Arm
from backend.payload.constants import PAYLOAD_FIXTURE_ENV_VAR
from backend.payload.detection import PayloadResidualCheck, evaluate_collision_misdetection
from backend.payload.gravity_reflection import PayloadGravityModel
from backend.payload.payload import Payload


@dataclass(frozen=True)
class RealPayloadVerification:
    """The verdict a real static-hold capture produced for a registered payload.

    Attributes:
        arm: The arm the capture held.
        payload_label: The declared registered payload's label.
        check: The residual check of the measured hold against the registered model.
        confirmed: True when the measured residual stays below the collision threshold on
            every joint — the registered mass/CoG matches the physical payload.
    """

    arm: Arm
    payload_label: str
    check: PayloadResidualCheck
    confirmed: bool


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(PAYLOAD_FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _verify_one(capture: dict[str, Any]) -> RealPayloadVerification:
    """Re-run the residual check over one real static-hold capture.

    Args:
        capture: One parsed capture record with `arm`, `pose_rad`, `measured_tau_nm`, and
            a `payload` block (`mass_kg`, `cog_m`, `label`).

    Returns:
        (RealPayloadVerification) The verdict; confirmed only when the residual stays below
        the collision threshold on every joint.
    """
    arm = Arm(str(capture["arm"]))
    payload_block = capture["payload"]
    payload = Payload.from_cog(
        mass_kg=float(payload_block["mass_kg"]),
        cog_m=[float(value) for value in payload_block["cog_m"]],
        label=str(payload_block.get("label", "")),
    )
    model = PayloadGravityModel(arm)
    model.registry.register(payload)
    pose = [float(value) for value in capture["pose_rad"]]
    measured = [float(value) for value in capture["measured_tau_nm"]]
    check = evaluate_collision_misdetection(model, pose, measured)
    return RealPayloadVerification(
        arm=arm,
        payload_label=payload.label,
        check=check,
        confirmed=not check.misdetected,
    )


def reverify_from_fixture(fixture_dir: Path) -> list[RealPayloadVerification]:
    """Re-run the payload residual check against real static-hold captures.

    Loads every `*.json` capture in the directory and re-applies the residual-vs-threshold
    check the offline acceptance exercises, now over the measured static-hold torque. This is
    the re-verification the deferred live-registration acceptance requires.

    Args:
        fixture_dir: Directory of captured static-hold JSON files.

    Returns:
        (list[RealPayloadVerification]) One verification per capture, ordered by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json static-hold capture in {fixture_dir}")
    return [_verify_one(json.loads(path.read_text(encoding="utf-8"))) for path in capture_files]
