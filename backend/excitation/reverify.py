"""The re-verification hook for the deferred on-arm injection (`WP-2B-06`).

The actual exciting-trajectory injection is torque-ON on a 40 Nm brakeless arm and does
not run on this host: it needs the `FR-MOT-058` torque path, real motors, and a
supervising operator. That acceptance is SKIPPED WITH A REASON, never asserted green (a
faked injection green is a safety lie — the friction fit and every downstream detector
would trust it). What ships instead is this hook: given a directory of recorded real
injection sessions, it re-checks the safety invariants the offline harness guarantees, so
a real run's evidence is validated by the same rules rather than assumed.

The recorded schema is one JSON object per session:

    {
      "torque_path_present": true,      # FR-MOT-058 path was wired (④)
      "dry_run_armed": true,            # WP-2A-00 dry-run gate had armed
      "safe_state_confirmed": true,     # safe initial state was confirmed (①)
      "segments": [                     # one drive per start()/resume()
        {"start_index": 0,
         "commanded_indices": [0, 1, 2],
         "abort": {"index": 3, "cause": "human_abort"}},
        {"start_index": 3, "commanded_indices": [3, 4, 5], "abort": null}
      ]
    }

The invariants below are exactly what `ExcitationInjector` produces (it stops *before*
commanding the abort tick and resumes from that index), so a genuine capture satisfies
them and a fixture that violates any of them fails the hook.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURE_ENV_VAR = "OPENARM_EXCITATION_REAL_FIXTURE"


@dataclass(frozen=True)
class ReverifyResult:
    """One invariant's verdict over one recorded session.

    Attributes:
        session: The session file name the verdict is for.
        check: The invariant name.
        passed: Whether the recorded session satisfied it.
        detail: A human-readable reason, especially on failure.
    """

    session: str
    check: str
    passed: bool
    detail: str


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory from the environment, or None when unset.

    Returns:
        (Path | None) The directory named by `OPENARM_EXCITATION_REAL_FIXTURE`, or None
        when the variable is unset — the signal the deferred acceptance stays skipped.
    """
    value = os.environ.get(FIXTURE_ENV_VAR)
    return Path(value) if value else None


def reverify_injection_sessions(fixture_dir: Path) -> list[ReverifyResult]:
    """Re-check every recorded injection session in a directory against the safety invariants.

    Args:
        fixture_dir: Directory of recorded session JSON files.

    Returns:
        (list[ReverifyResult]) One result per invariant per session; the overall run
        passes only when every result passed.

    Raises:
        FileNotFoundError: If `fixture_dir` does not exist or holds no session file.
    """
    if not fixture_dir.is_dir():
        raise FileNotFoundError(f"excitation fixture directory not found: {fixture_dir}")
    sessions = sorted(fixture_dir.glob("*.json"))
    if not sessions:
        raise FileNotFoundError(f"no session JSON files in excitation fixture: {fixture_dir}")

    results: list[ReverifyResult] = []
    for session in sessions:
        record = json.loads(session.read_text(encoding="utf-8"))
        results.extend(_reverify_one(session.name, record))
    return results


def _reverify_one(name: str, record: dict[str, Any]) -> list[ReverifyResult]:
    """Return the invariant verdicts for one recorded session."""
    segments = record.get("segments", [])
    return [
        _check_preconditions(name, record),
        _check_segments_contiguous(name, segments),
        _check_abort_stopped(name, segments),
        _check_resume_by_index(name, segments),
    ]


def _check_preconditions(name: str, record: dict[str, Any]) -> ReverifyResult:
    """Verify the three hard gates were recorded as held for the whole session."""
    missing = [
        key
        for key in ("torque_path_present", "dry_run_armed", "safe_state_confirmed")
        if not record.get(key, False)
    ]
    passed = not missing
    detail = "all three hard gates held" if passed else f"gate(s) not held: {', '.join(missing)}"
    return ReverifyResult(name, "preconditions_held", passed, detail)


def _check_segments_contiguous(name: str, segments: Sequence[dict[str, Any]]) -> ReverifyResult:
    """Verify each drive commanded a contiguous run starting at its start index."""
    for position, segment in enumerate(segments):
        start = segment.get("start_index", 0)
        commanded = list(segment.get("commanded_indices", []))
        expected = list(range(start, start + len(commanded)))
        if commanded != expected:
            return ReverifyResult(
                name,
                "segments_contiguous",
                False,
                f"segment {position} commanded {commanded}, expected contiguous {expected}",
            )
    return ReverifyResult(name, "segments_contiguous", True, "every drive was contiguous")


def _check_abort_stopped(name: str, segments: Sequence[dict[str, Any]]) -> ReverifyResult:
    """Verify an abort stopped the stream before the abort tick was ever commanded."""
    for position, segment in enumerate(segments):
        abort = segment.get("abort")
        if abort is None:
            continue
        abort_index = abort.get("index")
        commanded = list(segment.get("commanded_indices", []))
        if commanded and max(commanded) >= abort_index:
            return ReverifyResult(
                name,
                "abort_stopped_injection",
                False,
                f"segment {position} commanded index {max(commanded)} at/after its abort "
                f"index {abort_index}: the abort did not stop injection",
            )
    return ReverifyResult(name, "abort_stopped_injection", True, "every abort stopped the stream")


def _check_resume_by_index(name: str, segments: Sequence[dict[str, Any]]) -> ReverifyResult:
    """Verify each resume began at the trajectory index of the preceding abort (③)."""
    for position in range(len(segments) - 1):
        abort = segments[position].get("abort")
        if abort is None:
            return ReverifyResult(
                name,
                "resume_by_index",
                False,
                f"segment {position} has a successor but recorded no abort to resume from",
            )
        next_start = segments[position + 1].get("start_index")
        if next_start != abort.get("index"):
            return ReverifyResult(
                name,
                "resume_by_index",
                False,
                f"segment {position + 1} resumed at {next_start}, not the abort index "
                f"{abort.get('index')}",
            )
    return ReverifyResult(name, "resume_by_index", True, "every resume began at its abort index")
