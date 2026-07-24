"""The version pins that make a lineage record reproducible — elements (e)-(g).

`FR-TRN-054` (e)-(g) fix three environment facts a checkpoint's lineage must carry:
the training-code git SHA, the installed LeRobot version, and the container image
digest. `02c` §1.5 calls these the Wave 0-Ops version pins.

Two of the three are captured, not invented: the LeRobot version is read from the
installed distribution metadata (so a lockfile bump is recorded, never guessed),
and the code SHA is read from the working tree's `HEAD`. The third — the container
digest — is the one `FR-OPS-062` leaves open: when no container is adopted this
records the explicit `CONTAINER_NOT_USED` value rather than leaving the field
absent, because `02c` §1.5 makes field absence a distinct (and blocking) statement
from not-used.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from backend.training.lineage.constants import CONTAINER_NOT_USED, LEROBOT_DISTRIBUTION


@dataclass(frozen=True)
class VersionPins:
    """The three environment pins embedded immutably in a lineage record.

    Frozen because it is part of the immutable snapshot (`FR-TRN-054`): the pins a
    checkpoint was produced under never change after the fact.

    Attributes:
        code_sha: The training-code git commit the run executed (element (e)).
        lerobot_version: The installed LeRobot version the run used (element (f)).
        container_digest: The container image digest (element (g)), or
            `CONTAINER_NOT_USED` when no container was adopted — an explicit value,
            never an absent field (`02c` §1.5, CG-4A-05a).
    """

    code_sha: str
    lerobot_version: str
    container_digest: str


def installed_lerobot_version() -> str:
    """Return the installed LeRobot distribution version (element (f)).

    Returns:
        (str) The version string from distribution metadata.

    Raises:
        LineagePinError: When the LeRobot distribution is not installed, so the
            version cannot be recorded and a run must not proceed to lineage.
    """
    try:
        return metadata.version(LEROBOT_DISTRIBUTION)
    except metadata.PackageNotFoundError as missing:
        raise LineagePinError(
            f"LeRobot distribution {LEROBOT_DISTRIBUTION!r} is not installed; "
            "element (f) cannot be recorded"
        ) from missing


def git_head_sha(repo_root: Path) -> str:
    """Return the working tree's `HEAD` commit SHA, for element (e) capture.

    A convenience for a caller with no code SHA already in hand. The training
    launcher usually knows the exact code SHA it dispatched and should pass it to
    `capture_version_pins` directly; this helper is for the local-run case.

    Args:
        repo_root: The repository whose `HEAD` to read.

    Returns:
        (str) The full 40-character commit SHA.

    Raises:
        LineagePinError: When git cannot resolve `HEAD` (not a repo, or empty).
    """
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(repo_root),
        )
    except (OSError, subprocess.CalledProcessError) as failed:
        raise LineagePinError(
            f"cannot resolve git HEAD under {repo_root}; element (e) cannot be captured"
        ) from failed
    sha = completed.stdout.strip()
    if not sha:
        raise LineagePinError(
            f"git HEAD under {repo_root} is empty; element (e) cannot be captured"
        )
    return sha


def capture_version_pins(code_sha: str, container_digest: str = CONTAINER_NOT_USED) -> VersionPins:
    """Capture the three version pins, taking the code SHA the caller dispatched.

    The code SHA is a fact the caller (the launcher) knows exactly and must supply;
    the LeRobot version is read from the installed distribution; the container digest
    defaults to the explicit not-used value so a caller that adopted no container
    still records element (g) as a value rather than omitting it.

    Args:
        code_sha: The training-code git commit the run executed (element (e)).
        container_digest: The container image digest, or `CONTAINER_NOT_USED`.

    Returns:
        (VersionPins) The three captured pins.

    Raises:
        LineagePinError: When the code SHA is blank, or the LeRobot version cannot
            be read — either leaves an element unrecordable.
    """
    if not code_sha.strip():
        raise LineagePinError("code_sha is blank; element (e) cannot be recorded")
    return VersionPins(
        code_sha=code_sha.strip(),
        lerobot_version=installed_lerobot_version(),
        container_digest=container_digest,
    )


class LineagePinError(RuntimeError):
    """Raised when a version pin cannot be captured, so a run cannot record lineage.

    A pin that cannot be captured is not the same as a pin that is not-used: the
    former blocks (an element would be missing), the latter is recorded as an
    explicit value. This error is the blocking case.
    """
