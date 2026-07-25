"""The phase-2 (real-camera occupancy) re-verification hook — deferred, never faked.

WP-5-05 is two phases (`SHAPE-IM(2) → SHAPE-MS`): phase-1 is the synthetic load
harness and its judges (this tree), phase-2 is the real-camera-node occupancy
measurement, which is `AI-on-HW`. There is no camera on this host, so phase-2 is
DEFERRED. This hook is the honest seam: until the fixture env var points at a
real-capture directory, the phase-2 measurement is skipped WITH A REASON — it is never
asserted green and never invented. When a real capture is supplied, the on-rig run
ingests it through here; that path is exercised only when the fixture exists.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.loadtest.constants import PHASE2_FIXTURE_ENV_VAR


@dataclass(frozen=True)
class Phase2Status:
    """Whether the real-camera occupancy measurement ran, or why it did not.

    Attributes:
        ran: True only when a real-capture fixture was supplied and ingested.
        reason: Why it did not run, when it did not; empty when it ran.
        fixture_env_var: The env var a caller sets to point at a real capture.
        occupancy: The ingested real-camera occupancy record when it ran, else None.
    """

    ran: bool
    reason: str
    fixture_env_var: str
    occupancy: dict[str, Any] | None


def reverify_phase2_from_fixture() -> Phase2Status:
    """Run the phase-2 real-camera occupancy measurement if a fixture is present.

    Reads `PHASE2_FIXTURE_ENV_VAR`; when unset or pointing nowhere real, returns a
    skipped status with a reason. When it points at a JSON capture, ingests it as the
    occupancy record. The skip path is what keeps a HW-less host honest: no fixture
    means no measurement, not a fabricated pass.

    Returns:
        (Phase2Status) The outcome: ran with an occupancy record, or skipped with a
        reason.
    """
    fixture = os.environ.get(PHASE2_FIXTURE_ENV_VAR)
    if not fixture:
        return Phase2Status(
            ran=False,
            reason=(
                f"{PHASE2_FIXTURE_ENV_VAR} is unset; phase-2 real-camera occupancy is AI-on-HW "
                "and no camera exists on this host — deferred, not faked"
            ),
            fixture_env_var=PHASE2_FIXTURE_ENV_VAR,
            occupancy=None,
        )
    path = Path(fixture)
    if not path.is_file():
        return Phase2Status(
            ran=False,
            reason=f"{PHASE2_FIXTURE_ENV_VAR} points at {fixture!r}, which is not a file",
            fixture_env_var=PHASE2_FIXTURE_ENV_VAR,
            occupancy=None,
        )
    occupancy = json.loads(path.read_text(encoding="utf-8"))
    return Phase2Status(
        ran=True,
        reason="",
        fixture_env_var=PHASE2_FIXTURE_ENV_VAR,
        occupancy=occupancy,
    )
