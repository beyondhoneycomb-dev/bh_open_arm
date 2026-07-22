"""Real-fixture re-verification hook for the deferred physical capture (`02a` §4.1).

The physical open/close endpoint capture needs an operator and a live DM4310, so it
is deferred. This hook re-runs the full build-and-validate pipeline over a real
capture the moment one is supplied, so the deferral leaves a machine that runs rather
than a promise.

A fixture directory holds a `record.json` (the captured record: both sides' endpoint
rads, both sides' limits, the speed cap, the force cap) and an `expected.json` with
`{"loads": true|false}` — the verdict the captured config should produce. The hook
rebuilds the record through the same `from_json_dict` a normal load uses and reports
whether the load outcome matched. It is not a stub: the offline test drives it over a
synthetic-format capture and asserts both a matching and a mismatching case.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from backend.gripper_endpoint.errors import GripperConfigError
from backend.gripper_endpoint.schema import GripperMirrorRecord

FIXTURE_ENV_VAR = "OPENARM_GRIPPER_REAL_FIXTURE"

_RECORD_FILE = "record.json"
_EXPECTED_FILE = "expected.json"


@dataclass(frozen=True)
class ReverifyResult:
    """The outcome of re-verifying one captured record against its expectation.

    Attributes:
        source: The fixture directory re-verified.
        matched: True when the load outcome equalled the expected outcome.
        loaded: True when the captured record loaded (sign mirror + schema held).
        detail: A human-readable explanation, carrying the refusal reason on a load
            failure.
    """

    source: Path
    matched: bool
    loaded: bool
    detail: str


def fixture_dir_from_env() -> Path | None:
    """Return the real-capture fixture directory named by the environment, if set.

    Returns:
        (Path | None) The directory, or None when `OPENARM_GRIPPER_REAL_FIXTURE` is
        unset, which is what makes the hardware acceptance skip rather than fail.
    """
    raw = os.environ.get(FIXTURE_ENV_VAR)
    return Path(raw) if raw else None


def reverify_from_fixture(fixture_dir: Path) -> list[ReverifyResult]:
    """Re-run the load pipeline over a captured record and compare to its expectation.

    Args:
        fixture_dir: A directory holding `record.json` and `expected.json`.

    Returns:
        (list[ReverifyResult]) One result for the fixture directory.

    Raises:
        FileNotFoundError: If either fixture file is absent.
    """
    record_data = json.loads((fixture_dir / _RECORD_FILE).read_text(encoding="utf-8"))
    expected = json.loads((fixture_dir / _EXPECTED_FILE).read_text(encoding="utf-8"))
    expect_loads = bool(expected["loads"])

    loaded = True
    detail = "record loaded; sign mirror and per-unit force hold"
    try:
        GripperMirrorRecord.from_json_dict(record_data)
    except GripperConfigError as exc:
        loaded = False
        detail = f"record refused: {exc}"

    matched = loaded == expect_loads
    if not matched:
        verb = "loaded" if loaded else "was refused"
        detail = f"expected loads={expect_loads} but the captured record {verb}: {detail}"
    return [ReverifyResult(source=fixture_dir, matched=matched, loaded=loaded, detail=detail)]
