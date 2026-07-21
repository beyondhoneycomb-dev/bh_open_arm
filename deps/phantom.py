"""Reject every path that installs LeRobot by a resolvable semver spec.

`02a` §2.2 WP-ENV-01 interface contract: the pin is a commit SHA, not a semver,
and `pip install lerobot==0.6.1` / `==0.6.0` must both be refused. `0.6.1` is
refused because it is the phantom of `16` §3.1 — no PyPI release, no git tag. And
`0.6.0` is refused because a bare `==0.6.0` resolves the published wheel, whose
metadata cannot be distinguished from the 0.6.1-self-claiming source tree the pin
actually fixes; only a SHA addresses the exact tree.

This module is stdlib-only on purpose so the pin can be checked in the light CI
lane that never installs the robot stack.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The version string the upstream main branch self-claims but never released.
PHANTOM_VERSION = "0.6.1"
# The one version the project resolves to; still forbidden as a bare semver pin.
RESOLVED_VERSION = "0.6.0"

REASON_PHANTOM = "phantom-version"
REASON_SEMVER_PIN = "semver-pin"

# A dependency line that names lerobot and then applies a PEP 440 version operator.
# The operator group is what marks a *version-resolution* path, which the pin bans
# in favour of a SHA checkout.
_VERSION_OPERATOR = r"(==|===|~=|!=|<=|>=|<|>)"
_SPEC = re.compile(
    r"^\s*lerobot\s*(?:\[[^\]]*\])?\s*"
    + _VERSION_OPERATOR
    + r"\s*(?P<version>[0-9][0-9A-Za-z.*+!-]*)",
    re.IGNORECASE,
)
# A git/SHA checkout form, e.g. `lerobot @ git+https://...@<sha>` — the allowed shape.
_SHA_FORM = re.compile(r"git\+|@[0-9a-f]{7,40}\b", re.IGNORECASE)


@dataclass(frozen=True)
class Rejection:
    """Why a dependency spec is refused by the pin discipline.

    Attributes:
        spec: The offending dependency spec, verbatim.
        reason: `phantom-version` or `semver-pin`.
        version: The version the spec tried to resolve.
    """

    spec: str
    reason: str
    version: str

    def as_line(self) -> str:
        """Render the rejection as one report line.

        Returns:
            (str) Human-readable single line.
        """
        return f"REJECT [{self.reason}] {self.spec.strip()} (version={self.version})"


def is_phantom_version(version: str) -> bool:
    """Report whether a version string is the known phantom.

    Args:
        version: A bare version string such as `0.6.1`.

    Returns:
        (bool) True when the version never existed upstream.
    """
    return version.strip() == PHANTOM_VERSION


def reject_spec(spec: str) -> Rejection | None:
    """Judge one dependency spec against the SHA-pin discipline.

    A `git+`/`@<sha>` checkout form is allowed and returns None. Any spec that
    names lerobot with a version operator is refused: the phantom `0.6.1` as a
    phantom, every other version as a forbidden semver-resolution path.

    Args:
        spec: One dependency line, e.g. `lerobot==0.6.1`.

    Returns:
        (Rejection | None) The rejection, or None when the spec is allowed.
    """
    if _SHA_FORM.search(spec):
        return None
    match = _SPEC.match(spec)
    if not match:
        return None
    version = match.group("version")
    reason = REASON_PHANTOM if is_phantom_version(version) else REASON_SEMVER_PIN
    return Rejection(spec=spec, reason=reason, version=version)
