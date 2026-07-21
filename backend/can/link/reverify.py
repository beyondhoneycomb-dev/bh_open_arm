"""Real-fixture re-verification hook for link verification (acceptance ⑦, plan 02a §4.1).

Every runnable acceptance here is proven against synthetic `ip -details link show`
fixtures, because parsing is string processing (§4.2). What cannot be proven here is that
the parser reads a *real adapter's* output correctly: vcan has no bitrate concept and no
physical bus-error counters (§4.2 table), so the actual values are hardware's province.
That claim is deferred — not asserted green, not dropped.

This is the hook the deferral must ship: the moment a directory of real captured
`ip -details link show` outputs is supplied, `reverify_from_fixture` re-runs the exact
parse-and-validate pipeline over them and checks each verdict against a recorded
expectation. Until then the bound test skips with a reason. The capture directory holds
one `<iface>.txt` per channel plus an `expected.json` of
`{iface: {ok, state, fd, bitrate, dbitrate}}`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from backend.can.link.parser import LinkState, parse_link_show
from backend.can.link.validator import LinkVerdict, validate_link

# Environment variable a caller sets to point the hook at a real capture directory.
FIXTURE_ENV_VAR = "OPENARM_LINK_REAL_FIXTURE"
EXPECTED_FILENAME = "expected.json"
CAPTURE_SUFFIX = ".txt"


@dataclass(frozen=True)
class ReverifyResult:
    """Outcome of re-verifying one real capture against its expectation.

    Attributes:
        iface: Interface the capture is for.
        state: Parsed link state from the real capture.
        verdict: Verdict the pipeline produced.
        matched: True when the parse and verdict matched the recorded expectation.
        detail: Human-readable mismatch detail, empty on a match.
    """

    iface: str
    state: LinkState
    verdict: LinkVerdict
    matched: bool
    detail: str


def fixture_dir_from_env() -> Path | None:
    """Return the real-capture directory named by the environment, if set and present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def reverify_from_fixture(fixture_dir: Path) -> list[ReverifyResult]:
    """Re-run parse-and-validate over real captured link-show outputs.

    This is the identical pipeline the synthetic tests run, pointed at real bytes.

    Args:
        fixture_dir: Directory of `<iface>.txt` captures plus `expected.json`.

    Returns:
        (list[ReverifyResult]) One result per interface in `expected.json`, sorted.

    Raises:
        FileNotFoundError: If `expected.json`, or a named capture file, is missing.
    """
    expected_path = fixture_dir / EXPECTED_FILENAME
    if not expected_path.is_file():
        raise FileNotFoundError(f"missing {EXPECTED_FILENAME} in {fixture_dir}")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    results: list[ReverifyResult] = []
    for iface, want in sorted(expected.items()):
        capture = fixture_dir / f"{iface}{CAPTURE_SUFFIX}"
        if not capture.is_file():
            raise FileNotFoundError(f"missing capture {capture.name} in {fixture_dir}")
        state = parse_link_show(capture.read_text(encoding="utf-8"), iface)
        verdict = validate_link(state)
        results.append(_compare(iface, state, verdict, want))
    return results


def _compare(
    iface: str, state: LinkState, verdict: LinkVerdict, want: dict[str, object]
) -> ReverifyResult:
    """Compare a real-capture verdict against a recorded expectation.

    Args:
        iface: Interface under check.
        state: Parsed state from the real capture.
        verdict: Verdict produced for it.
        want: Expected fields; any of `ok`, `state`, `fd`, `bitrate`, `dbitrate`.

    Returns:
        (ReverifyResult) The comparison outcome.
    """
    mismatches: list[str] = []
    if "ok" in want and verdict.ok != want["ok"]:
        mismatches.append(f"ok {verdict.ok} != {want['ok']}")
    for field in ("state", "fd", "bitrate", "dbitrate"):
        if field in want and getattr(state, field) != want[field]:
            mismatches.append(f"{field} {getattr(state, field)!r} != {want[field]!r}")
    return ReverifyResult(
        iface=iface,
        state=state,
        verdict=verdict,
        matched=not mismatches,
        detail="; ".join(mismatches),
    )
