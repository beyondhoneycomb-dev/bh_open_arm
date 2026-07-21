"""Load and validate the LeRobot commit-SHA pin.

`02a` §2.2 WP-ENV-01 acceptance ①: the pin records that the source self-claims
`0.6.1` while `resolved_version` is `0.6.0`, and asserts that this mismatch is
intended. This module is the machine reading of that record — stdlib only, so it
runs in the light lane.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PIN_PATH = Path(__file__).resolve().parent / "lerobot.pin"

_SHA_LEN = 40
_REQUIRED_KEYS = ("repo_url", "commit_sha", "tree_hash", "resolved_version")


@dataclass(frozen=True)
class PinReport:
    """The result of validating the pin document.

    Attributes:
        ok: True when the pin is well-formed and the version mismatch is declared
            intended.
        problems: One line per defect; empty when `ok`.
        commit_sha: The pinned commit, echoed for callers computing env_hash.
        resolved_version: The version the pin resolves to.
        self_claimed_version: The version the upstream source self-claims.
    """

    ok: bool
    problems: tuple[str, ...]
    commit_sha: str
    resolved_version: str
    self_claimed_version: str


def load_pin(path: Path = PIN_PATH) -> dict[str, object]:
    """Parse the pin JSON document.

    Args:
        path: Path to `deps/lerobot.pin`.

    Returns:
        (dict[str, object]) The parsed mapping.

    Raises:
        TypeError: When the document does not parse to a mapping.
    """
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} did not parse to a mapping")
    return loaded


def validate_pin(document: dict[str, object]) -> PinReport:
    """Validate the pin shape and the intended version mismatch (acceptance ①).

    Args:
        document: The parsed pin mapping.

    Returns:
        (PinReport) Verdict with per-defect problem lines.
    """
    problems: list[str] = []
    for key in _REQUIRED_KEYS:
        if not document.get(key):
            problems.append(f"missing required key: {key}")

    commit_sha = str(document.get("commit_sha", ""))
    if commit_sha and (len(commit_sha) != _SHA_LEN or not _is_hex(commit_sha)):
        problems.append(f"commit_sha is not a 40-char hex sha: {commit_sha!r}")

    tree_hash = str(document.get("tree_hash", ""))
    if tree_hash and (len(tree_hash) != _SHA_LEN or not _is_hex(tree_hash)):
        problems.append(f"tree_hash is not a 40-char hex sha: {tree_hash!r}")

    resolved = str(document.get("resolved_version", ""))
    self_claimed = str(document.get("self_claimed_version", ""))
    intended = bool(document.get("version_mismatch_intended", False))

    # Acceptance ①: the mismatch must be present AND declared intended. A pin
    # whose two versions agree would mean the phantom claim silently evaporated,
    # which is exactly the drift this record exists to keep visible.
    if self_claimed == resolved:
        problems.append(
            f"self_claimed_version and resolved_version agree ({resolved!r}); "
            "the intended 0.6.1-vs-0.6.0 mismatch is not recorded"
        )
    elif not intended:
        problems.append(
            f"version mismatch {self_claimed!r} != {resolved!r} is present but "
            "not asserted intended (version_mismatch_intended is false)"
        )

    return PinReport(
        ok=not problems,
        problems=tuple(problems),
        commit_sha=commit_sha,
        resolved_version=resolved,
        self_claimed_version=self_claimed,
    )


def _is_hex(text: str) -> bool:
    """Report whether a string is all lowercase-or-uppercase hex digits."""
    try:
        int(text, 16)
    except ValueError:
        return False
    return True
