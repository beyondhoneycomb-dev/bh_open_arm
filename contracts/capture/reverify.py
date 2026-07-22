"""Re-verification hook: re-run the CTR-CAP sidecar checks over a capture fixture.

`02b` §5.2 WP-3A-02 ③ asks that, on a device exposing a hardware clock and frame
counter, host↔sensor offset/drift and frame-number continuity are *verified* — not
asserted once and forgotten. This hook is the machinery that re-runs that
verification over a capture: it reloads a per-episode sidecar, re-validates its
shape, recomputes each slot's offset drift and frame-number continuity, and
compares them to a recorded expectation.

The machinery is exercised offline against synthetic captures (a fixture directory
the tests write). The real-device leg — a genuine RealSense capture whose hardware
timestamps this hook re-derives — is deferred behind `OPENARM_CAP_REAL_FIXTURE`,
because it needs hardware this environment does not have. The two together are the
honest shape: the pipeline runs here, only the real sensor bytes are pending.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from contracts.capture.schema import (
    CameraSlotKey,
    CaptureSidecar,
    frame_numbers_continuous,
    host_sensor_offsets,
    offset_drift_span,
    sidecar_from_records,
    slot_frame_numbers,
)

# The environment variable pointing at a real-device capture fixture directory.
# Unset in the offline environment, which is why the real-hardware test skips.
REAL_FIXTURE_ENV = "OPENARM_CAP_REAL_FIXTURE"

# The two files a fixture directory holds: the flattened sidecar records, and the
# expectation the reload is checked against.
SIDECAR_FILE = "sidecar.json"
EXPECTED_FILE = "expected.json"


@dataclass(frozen=True)
class ReverifyResult:
    """The outcome of re-verifying one camera slot against its expectation.

    Attributes:
        slot: The camera slot re-verified.
        matched: Whether the recomputed checks matched the recorded expectation.
        offset_drift_ns: The recomputed peak-to-peak host↔sensor offset drift.
        continuous: Whether the recomputed frame-number series had no gaps.
        detail: A human-readable description of a mismatch, empty when matched.
    """

    slot: str
    matched: bool
    offset_drift_ns: int
    continuous: bool
    detail: str


def fixture_dir_from_env() -> Path | None:
    """Return the real-device fixture directory, when one is configured.

    Returns:
        (Path | None) The directory `OPENARM_CAP_REAL_FIXTURE` names, or None.
    """
    value = os.environ.get(REAL_FIXTURE_ENV)
    return Path(value) if value else None


def reverify_from_fixture(fixture_dir: Path) -> list[ReverifyResult]:
    """Re-run the sidecar checks over one fixture directory.

    Reloads and re-validates the sidecar, then for each slot named in the
    expectation recomputes offset drift and frame-number continuity and compares
    them: the drift must not exceed the recorded bound, and continuity must match.

    Args:
        fixture_dir: A directory holding `sidecar.json` and `expected.json`.

    Returns:
        (list[ReverifyResult]) One result per expected slot, in expectation order.

    Raises:
        FileNotFoundError: If either fixture file is absent.
    """
    sidecar_doc = json.loads((fixture_dir / SIDECAR_FILE).read_text(encoding="utf-8"))
    expected = json.loads((fixture_dir / EXPECTED_FILE).read_text(encoding="utf-8"))

    sidecar: CaptureSidecar = sidecar_from_records(
        episode_index=sidecar_doc["episode_index"],
        records=sidecar_doc["records"],
    )

    results: list[ReverifyResult] = []
    for slot_value, slot_expected in expected.get("slots", {}).items():
        slot = CameraSlotKey(slot_value)
        drift = offset_drift_span(host_sensor_offsets(sidecar, slot))
        continuous = frame_numbers_continuous(slot_frame_numbers(sidecar, slot))

        max_drift = slot_expected["max_offset_drift_ns"]
        want_continuous = slot_expected["frame_numbers_continuous"]
        mismatch = []
        if drift > max_drift:
            mismatch.append(f"offset drift {drift} ns exceeds bound {max_drift} ns")
        if continuous != want_continuous:
            mismatch.append(f"continuity {continuous} != expected {want_continuous}")

        results.append(
            ReverifyResult(
                slot=slot_value,
                matched=not mismatch,
                offset_drift_ns=drift,
                continuous=continuous,
                detail="; ".join(mismatch),
            )
        )
    return results
