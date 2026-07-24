"""WP-4B-05 — CG-4B-05c: the LeRobot pin is a commit SHA and the ghost is absent.

`FR-OPS-067` pins LeRobot by commit SHA, not semver, because the ghost version never
shipped — no PyPI release, no git tag (`16` §3.1). The one place the ghost literal is
named is `deps.phantom.PHANTOM_VERSION`; this module references that symbol and never
writes the literal, so `deps/phantom.py` stays its single source and this module's own
files pass the same scan they apply. The check enforces two things without importing
the robot stack:

- The operative pin resolves by commit SHA to `deps.phantom.RESOLVED_VERSION`. The
  pin reading and the phantom-spec grammar are reused from `deps.pin`/`deps.phantom` —
  no second copy of either rule lives here.
- The ghost appears in no *operative* location: not in this band's registration
  artifacts, and not as a resolvable dependency spec in `pyproject.toml`/`uv.lock`.

`deps/lerobot.pin` is deliberately out of that scan. Its `self_claimed_version` field
records the ghost on purpose — that field *documents* the mismatch so the pin can
assert it is intended, which `deps.pin.validate_pin` verifies. Flagging it would
punish the one file whose job is to name the ghost and refuse it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from deps import phantom, pin

REPO_ROOT = Path(__file__).resolve().parents[3]
PIN_PATH = REPO_ROOT / "deps" / "lerobot.pin"

# Operative dependency-resolution files: a spec here decides what pip/uv installs, so
# the ghost must not appear in either — as a spec or as a bare literal.
DEPENDENCY_SPEC_FILES = ("pyproject.toml", "uv.lock")

# This band's own registration artifacts must reference the SHA, never the ghost.
OWNED_DIR = Path(__file__).resolve().parent

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_LEROBOT_LINE = re.compile(r"lerobot", re.IGNORECASE)


@dataclass(frozen=True)
class GhostVerdict:
    """The outcome of the ghost-version static check.

    Attributes:
        ok: True when the pin is a SHA and the ghost appears in no operative place.
        problems: One line per violation; empty when `ok`.
        commit_sha: The pinned commit, echoed for the report.
        resolved_version: The version the pin resolves to.
    """

    ok: bool
    problems: tuple[str, ...]
    commit_sha: str
    resolved_version: str

    def as_line(self) -> str:
        """Render the verdict as one report line.

        Returns:
            (str) A PASS/FAIL line; on failure it names the problems.
        """
        if self.ok:
            return (
                f"ghost-version PASS — pinned by SHA {self.commit_sha[:12]} "
                f"@ {self.resolved_version}"
            )
        return "ghost-version FAIL — " + "; ".join(self.problems)


def _pin_problems() -> tuple[list[str], str, str]:
    """Validate the pin is a well-formed commit-SHA pin resolving to 0.6.0.

    Returns:
        (tuple) Problems, the commit SHA, and the resolved version.
    """
    problems: list[str] = []
    document = pin.load_pin(PIN_PATH)
    report = pin.validate_pin(document)
    if not report.ok:
        problems.extend(report.problems)
    if not _SHA_RE.match(report.commit_sha or ""):
        problems.append(
            f"commit_sha {report.commit_sha!r} is not a 40-hex commit SHA (semver pin?)"
        )
    if report.resolved_version != phantom.RESOLVED_VERSION:
        problems.append(
            f"resolved_version {report.resolved_version!r} is not {phantom.RESOLVED_VERSION!r}"
        )
    if report.resolved_version == phantom.PHANTOM_VERSION:
        problems.append(f"resolved_version is the ghost {phantom.PHANTOM_VERSION}")
    return problems, report.commit_sha, report.resolved_version


def _dependency_spec_problems() -> list[str]:
    """Refuse a ghost spec or a bare ghost literal in the dependency-resolution files.

    Returns:
        (list[str]) One line per violating file/line.
    """
    problems: list[str] = []
    for name in DEPENDENCY_SPEC_FILES:
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _LEROBOT_LINE.search(line):
                rejection = phantom.reject_spec(line)
                if rejection is not None and rejection.reason == phantom.REASON_PHANTOM:
                    problems.append(f"{name}:{lineno} pins the ghost — {rejection.as_line()}")
            if phantom.PHANTOM_VERSION in line:
                problems.append(
                    f"{name}:{lineno} contains the ghost literal {phantom.PHANTOM_VERSION}"
                )
    return problems


def _owned_artifact_problems() -> list[str]:
    """Refuse the ghost literal anywhere in this band's registration artifacts.

    Returns:
        (list[str]) One line per file that names the ghost.
    """
    problems: list[str] = []
    for path in sorted(OWNED_DIR.rglob("*")):
        if not path.is_file() or path.suffix == ".pyc" or "__pycache__" in path.parts:
            continue
        if phantom.PHANTOM_VERSION in path.read_text(encoding="utf-8"):
            relative = path.relative_to(REPO_ROOT)
            problems.append(f"{relative} contains the ghost literal {phantom.PHANTOM_VERSION}")
    return problems


def check_ghost_version() -> GhostVerdict:
    """Run the CG-4B-05c static check over the committed tree.

    Returns:
        (GhostVerdict) Blocked (`ok=False`) when the pin is not a SHA or the ghost
            appears in any operative location.
    """
    pin_problems, commit_sha, resolved_version = _pin_problems()
    problems = [*pin_problems, *_dependency_spec_problems(), *_owned_artifact_problems()]
    return GhostVerdict(
        ok=not problems,
        problems=tuple(problems),
        commit_sha=commit_sha,
        resolved_version=resolved_version,
    )
