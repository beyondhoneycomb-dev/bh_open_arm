"""Auto-upgrade blocker: reject any version-contract pin a resolver could advance.

`09` FR-SIM-102 / U-3 make no-auto-upgrade the contract. This module is the standalone
validator that enforces it over the pin manifest (WP-OPS-03 acceptance ①): given a
version specifier, it decides whether the specifier freezes a single version — or a
single minor line whose patch is allowed to float — versus whether it hands the
resolver latitude to pick something newer.

This is a validator invoked by tests, not a CI rule (CI-01..CI-18 are owned elsewhere).
Its scope is the version-contract pins the manifest declares (Isaac Sim/Lab): those are
the pins U-3 freezes. It deliberately does NOT police general pip dependency ranges in
`pyproject.toml` — resolving those is WP-ENV-02's lockfile remit, and a `>=` there is a
tooling range, not a contract violation.

The classifier fails closed: a specifier it cannot prove EXACT is treated as a RANGE and
rejected. An unrecognised spec is not silently trusted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

# Operators and tokens that let a resolver advance the pinned minor/major line. `~=`
# is a compatible-release range (`~=2.3` admits 2.4, 2.5, ...), not a patch pin, so it
# floats the minor and is forbidden exactly as `>=` is. A comma joins two constraints
# into a range, and a bare wildcard/"latest" names no version at all. `>=` precedes `>`
# in the tuple so a two-character operator is reported whole rather than as its prefix.
_FORBIDDEN_OPERATORS = (">=", "<=", "!=", "~=", ">", "<", "~", "^")
_BARE_FLOATERS = frozenset({"", "*", "latest", "x", "X"})

# An exact numeric version, optionally written with a leading `==`: `5`, `5.1`, `5.1.0`.
_EXACT_NUMERIC = re.compile(r"^(?:==?\s*)?\d+(?:\.\d+)*$")
# A frozen-minor patch line: a trailing `.*`/`.x` wildcard is allowed ONLY after at
# least major.minor, so `2.3.x` / `==2.3.*` freeze the 2.3 minor and float the patch
# (U-3's "2.3.x"), while `2.*` — a wildcard on the minor — is not exact and is rejected.
_EXACT_PATCH_WILDCARD = re.compile(r"^(?:==?\s*)?\d+\.\d+(?:\.\d+)*\.(?:\*|x|X)$")
_COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


class Classification(Enum):
    """Whether a specifier freezes a version or lets a resolver advance it."""

    EXACT = "exact"
    RANGE = "range"


@dataclass(frozen=True)
class SpecifierVerdict:
    """The classification of one version specifier and why.

    Attributes:
        specifier: The specifier as written.
        classification: EXACT (frozen) or RANGE (auto-upgradeable).
        reason: For a RANGE, the operator or token that floats it; empty for EXACT.
        where: A caller-supplied label for the pin site, echoed for diagnostics.
    """

    specifier: str
    classification: Classification
    reason: str
    where: str

    @property
    def rejected(self) -> bool:
        """Whether this specifier violates the no-auto-upgrade contract."""
        return self.classification is Classification.RANGE


def classify_specifier(specifier: str, where: str = "") -> SpecifierVerdict:
    """Classify a version specifier as EXACT or RANGE.

    A specifier is EXACT when it names exactly one version, or one minor line whose
    patch floats (`2.3.x` / `==2.3.*`), or a 40-char commit SHA. Everything else —
    every inequality, compatible-release, caret, comma-joined constraint, and bare
    wildcard — is RANGE, and so is anything the patterns do not recognise (fail closed).

    Args:
        specifier: The version specifier, e.g. `==5.1.0`, `2.3.x`, `>=2.3`, or a SHA.
        where: Optional label for the pin site, echoed in the verdict.

    Returns:
        (SpecifierVerdict) The classification and, when RANGE, the floating token.
    """
    text = specifier.strip()

    if text.lower() in {t.lower() for t in _BARE_FLOATERS}:
        return SpecifierVerdict(
            specifier, Classification.RANGE, f"names no fixed version ({text!r})", where
        )

    if _COMMIT_SHA.match(text):
        return SpecifierVerdict(specifier, Classification.EXACT, "", where)

    floating = _floating_token(text)
    if floating is not None:
        return SpecifierVerdict(
            specifier,
            Classification.RANGE,
            f"range operator {floating!r} lets the resolver advance the pin",
            where,
        )

    if _EXACT_NUMERIC.match(text) or _EXACT_PATCH_WILDCARD.match(text):
        return SpecifierVerdict(specifier, Classification.EXACT, "", where)

    return SpecifierVerdict(
        specifier,
        Classification.RANGE,
        f"unrecognised specifier, not provably exact ({text!r})",
        where,
    )


def _floating_token(text: str) -> str | None:
    """Return the first forbidden operator/token that floats a specifier, or None.

    A trailing `.*` (as in `==2.3.*`) is a frozen-minor patch wildcard, not a bare
    floater, so it is not reported here; a bare `*` was already caught upstream.

    Args:
        text: A stripped specifier.

    Returns:
        (str | None) The floating token, or None when nothing floats the specifier.
    """
    for operator in _FORBIDDEN_OPERATORS:
        if operator in text:
            return operator
    if "," in text:
        return ","
    # A `*` anywhere other than a trailing `.*` prefix-match floats the version.
    star = text.find("*")
    if star != -1 and not text.endswith(".*"):
        return "*"
    return None


def scan_specifiers(specifiers: dict[str, str]) -> tuple[SpecifierVerdict, ...]:
    """Classify a mapping of pin-site label to specifier.

    Args:
        specifiers: Pin-site label to version specifier.

    Returns:
        (tuple[SpecifierVerdict, ...]) One verdict per specifier, in sorted label order.
    """
    return tuple(
        classify_specifier(spec, where=label) for label, spec in sorted(specifiers.items())
    )


def manifest_specifiers(manifest: dict[str, Any]) -> dict[str, str]:
    """Extract the version-contract specifiers a manifest declares.

    Only pins carrying an explicit `spec` (the declared Isaac Sim/Lab pins) are
    version-contract specifiers. `kind: commit_sha` and `kind: resolved` pins are
    referenced upstream artifacts, not specifiers this blocker owns.

    Args:
        manifest: A parsed pin manifest mapping.

    Returns:
        (dict[str, str]) Pin-site label to specifier for every pin declaring a `spec`.
    """
    out: dict[str, str] = {}
    pins = manifest.get("pins", {})
    if isinstance(pins, dict):
        for name, body in pins.items():
            if isinstance(body, dict) and "spec" in body:
                out[f"pins.{name}"] = str(body["spec"])
    return out


def scan_manifest(manifest: dict[str, Any]) -> tuple[SpecifierVerdict, ...]:
    """Classify every version-contract specifier a manifest declares.

    Args:
        manifest: A parsed pin manifest mapping.

    Returns:
        (tuple[SpecifierVerdict, ...]) One verdict per declared specifier.
    """
    return scan_specifiers(manifest_specifiers(manifest))


def rejected(verdicts: tuple[SpecifierVerdict, ...]) -> tuple[SpecifierVerdict, ...]:
    """Filter a verdict tuple down to the rejected (RANGE) specifiers.

    Args:
        verdicts: Verdicts from `scan_*`.

    Returns:
        (tuple[SpecifierVerdict, ...]) Only the specifiers that violate the contract.
    """
    return tuple(v for v in verdicts if v.rejected)
