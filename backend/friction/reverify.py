"""Real-fixture re-verification hook for the deferred PG-FRIC-001 pass (§2.0, THE ONE RULE).

On this host the identification math runs on synthetic logs; what cannot run is the real pass,
which needs real excitation logs (WP-2B-06, torque-ON on a brakeless 40 Nm arm) and a PG-J7-001
torque-scale pass, of which this host has neither. That acceptance is skipped with a reason,
never asserted green.

This is the hook the deferral ships. The moment a directory of real captures is supplied via
`OPENARM_FRICTION_REAL_FIXTURE`, `reverify_from_fixture` re-runs the *identical* fit and
separation over the real numbers — the same `identify_friction` and `separation_stats`, with
the same thresholds — and reports whether each joint converged and separated. It renders no
PG-FRIC-001 verdict on its own: the torque-scale precondition PG-J7-001 is a hardware gate the
hook cannot evaluate, so it reports the fit evidence and leaves the pass decision to the
acceptance runner that also checks PG-J7-001. The hook can never manufacture a green the offline
path would not, because it is the offline path pointed at real data.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from backend.friction.basis import InverseDynamicsBasis
from backend.friction.constants import FIXTURE_ENV_VAR
from backend.friction.errors import FrictionIdentificationError
from backend.friction.identify import identify_friction
from backend.friction.log import ExcitationLog
from backend.friction.model import FrictionParams
from backend.friction.seed import V1_SEED_FRICTION
from backend.friction.separation import separation_stats
from backend.gravity import Arm


@dataclass(frozen=True)
class RealFrictionVerification:
    """The fit evidence a single real capture produced.

    Attributes:
        capture_id: The capture's identifier (its filename stem by default).
        log_freq_hz: The logging rate of the real capture.
        all_converged: Whether every joint's fit converged.
        all_separated: Whether every joint's residual separated from the model signals.
        per_joint_separated: The separation verdict per joint, joint1..joint7 order.
        torque_scale_precondition: The external gate a real pass still requires — a constant
            reminder that this evidence is not a PG-FRIC-001 pass without PG-J7-001.
    """

    capture_id: str
    log_freq_hz: float
    all_converged: bool
    all_separated: bool
    per_joint_separated: tuple[bool, ...]
    torque_scale_precondition: str


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _log_from_capture(capture: dict[str, Any]) -> ExcitationLog:
    """Build an excitation log from one parsed real capture.

    Args:
        capture: A parsed capture mapping with `log_freq_hz` and `q`/`qd`/`qdd`/`tau` arrays.

    Returns:
        (ExcitationLog) The capture as a log.

    Raises:
        FrictionIdentificationError: If a required channel is missing.
    """
    try:
        return ExcitationLog(
            q=np.asarray(capture["q"], dtype=np.float64),
            qd=np.asarray(capture["qd"], dtype=np.float64),
            qdd=np.asarray(capture["qdd"], dtype=np.float64),
            tau=np.asarray(capture["tau"], dtype=np.float64),
            log_freq_hz=float(capture["log_freq_hz"]),
        )
    except KeyError as missing:
        raise FrictionIdentificationError(
            f"real capture is missing required channel {missing}"
        ) from missing


def _verify_one(
    capture_id: str,
    capture: dict[str, Any],
    basis: InverseDynamicsBasis,
    seed: tuple[FrictionParams, ...],
) -> RealFrictionVerification:
    """Re-run the identical fit and separation over one real capture.

    Args:
        capture_id: The capture identifier.
        capture: The parsed capture mapping.
        basis: The inverse-dynamics basis for the arm.
        seed: The per-joint warm-start (v1 seed).

    Returns:
        (RealFrictionVerification) The fit evidence from the real numbers.
    """
    log = _log_from_capture(capture)
    result = identify_friction(log, basis, seed)
    stats = separation_stats(result)
    per_joint = tuple(stat.separated for stat in stats)
    return RealFrictionVerification(
        capture_id=capture_id,
        log_freq_hz=log.log_freq_hz,
        all_converged=all(fit.converged for fit in result.fits),
        all_separated=all(per_joint),
        per_joint_separated=per_joint,
        torque_scale_precondition="PG-J7-001 PASS required; not evaluated by this hook",
    )


def reverify_from_fixture(
    fixture_dir: Path, arm: Arm = Arm.RIGHT, seed: tuple[FrictionParams, ...] = V1_SEED_FRICTION
) -> list[RealFrictionVerification]:
    """Re-run the friction identification against real captured excitation logs.

    Loads every `*.json` capture in the directory and runs the identical fit and separation the
    offline demonstration exercises, now pointed at real numbers. This is the re-verification
    the deferred hardware acceptance requires.

    Args:
        fixture_dir: Directory of captured excitation JSON files, one per session.
        arm: Which arm the captures are for.
        seed: The per-joint warm-start (v1 seed).

    Returns:
        (list[RealFrictionVerification]) One verification per capture file, ordered by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json friction capture in {fixture_dir}")
    basis = InverseDynamicsBasis(arm)
    return [
        _verify_one(path.stem, json.loads(path.read_text(encoding="utf-8")), basis, seed)
        for path in capture_files
    ]
