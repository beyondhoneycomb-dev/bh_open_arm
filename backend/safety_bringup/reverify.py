"""Real-fixture re-verification for the deferred command-following sweep (`02a` §4.1).

Most of WP-1-06 runs on this host: the link7 collision check over the committed MJCF, the
margin policy, the threshold floor, the detection-method and octomap checks, the whole
velocity derivation and its three-way table, the bootstrap limiter, and the sweep
*publication gate*. What does not run here is the command-following sweep itself (⑨-a/⑨-b):
it needs the powered arm under the bootstrap limiter, single joint, mechanically
constrained, and there is no CAN adapter, no motor, and no PG-SAFE-001 PASS on this host.
It is deferred — skipped with a reason, never asserted green.

This is the hook that deferral ships. When a directory of real single-joint sweep captures
is supplied via `OPENARM_SAFETY_BRINGUP_REAL_FIXTURE`, `reverify_from_fixture` re-runs the
*identical* publication gate — the three constraints and the zero-commands-over-limiter
check — against the real samples, and only then computes the tracking error from the
measured column. A capture that dropped a constraint or commanded over the limiter is
refused exactly as it would be offline, so the hook can never manufacture the sweep pass
`THE ONE RULE` forbids: the bootstrap limiter is read from the derivation, never from the
capture, so an observation cannot raise its own ceiling.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.safety_bringup.constants import FIXTURE_ENV_VAR
from backend.safety_bringup.sweep import (
    SweepConstraints,
    SweepPublication,
    SweepSample,
    assert_sweep_publishable,
)


@dataclass(frozen=True)
class RealSweepVerification:
    """The verdict a real single-joint sweep capture produced.

    Attributes:
        joint_index: The joint the capture swept.
        publication: The admitted sweep, with its real tracking-error vector; None when the
            capture was refused by the publication gate.
        refusal: The refusal reason when the capture failed a constraint, else empty.
    """

    joint_index: int
    publication: SweepPublication | None
    refusal: str


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


def _verify_one(capture: dict[str, Any]) -> RealSweepVerification:
    """Re-run the publication gate over one real sweep capture.

    Args:
        capture: One parsed capture record.

    Returns:
        (RealSweepVerification) The verdict; publication set only when the gate admitted it.
    """
    joint_index = int(capture["joint_index"])
    constraints = SweepConstraints(
        single_joint=bool(capture["single_joint"]),
        mechanically_constrained=bool(capture["mechanically_constrained"]),
    )
    samples = tuple(
        SweepSample(
            commanded_rad_s=float(sample["commanded_rad_s"]),
            measured_rad_s=float(sample["measured_rad_s"]),
        )
        for sample in capture.get("samples", [])
    )
    try:
        publication = assert_sweep_publishable(joint_index, samples, constraints)
    except Exception as refusal:  # noqa: BLE001 — the refusal reason is the reported verdict
        return RealSweepVerification(
            joint_index=joint_index, publication=None, refusal=str(refusal)
        )
    return RealSweepVerification(joint_index=joint_index, publication=publication, refusal="")


def reverify_from_fixture(fixture_dir: Path) -> list[RealSweepVerification]:
    """Re-run the sweep publication gate against real single-joint sweep captures.

    Loads every `*.json` capture in the directory and re-applies the three-constraint gate
    and the limiter-overrun check the offline tests exercise, now over real commanded and
    measured velocities. This is the re-verification the deferred sweep acceptances require.

    Args:
        fixture_dir: Directory of captured sweep JSON files, one per joint.

    Returns:
        (list[RealSweepVerification]) One verification per capture, ordered by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json sweep capture in {fixture_dir}")
    return [_verify_one(json.loads(path.read_text(encoding="utf-8"))) for path in capture_files]
