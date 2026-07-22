"""Static proof of the single-gateway property: `DetectionActivation` has one constructor (③).

The gate is SHAPE-IG — the single gateway for 2C real activation. That is only true if no consumer
builds a `DetectionActivation` directly: a second constructor could recompute the speed cap or the
banner inconsistently, and a degrade accepted there would bypass `resolve_activation`'s downgrade.
Combined with `__post_init__` (which makes a silent-downgrade object impossible to construct at
all), this scan is what closes the "0 paths that silently pass a downgrade" acceptance: the type
cannot be built silently, and it cannot be built anywhere but the gate.

The scan mirrors WP-1-06's deprecated-pipeline scan: it counts textual construction sites and
excludes the paths that name the symbol as its own definition or as data (the gate module, this
checker, the package `__init__` re-export), the same way the 0xFE sender scan excludes its detector.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# The constructor call the single-gateway property forbids outside the gate module.
ACTIVATION_CONSTRUCTOR = "DetectionActivation("

PYTHON_GLOB = "*.py"


@dataclass(frozen=True)
class ActivationConstructionSite:
    """One `DetectionActivation(` construction found outside the gate module (③).

    Attributes:
        path: The file the construction was found in.
        line: One-based line number.
    """

    path: Path
    line: int


def scan_activation_construction(
    roots: tuple[Path, ...], exclude: tuple[Path, ...]
) -> list[ActivationConstructionSite]:
    """Scan Python sources for `DetectionActivation(` construction; the count must be zero (③).

    `resolve_activation` is the sole legal constructor, so every match outside the excluded paths
    is a second gateway. The excluded roots are the paths that name the constructor as a definition
    or as data — the gate module itself, this checker, and the package `__init__` re-export — which
    are not consumer constructions.

    Args:
        roots: Directories to scan recursively for `*.py`.
        exclude: Paths (files or directories) whose matches are the definition or data, not
            consumer constructions.

    Returns:
        (list[ActivationConstructionSite]) Every construction site found, empty when clean.
    """
    sites: list[ActivationConstructionSite] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob(PYTHON_GLOB)):
            if _is_excluded(path, exclude):
                continue
            for line_number, text in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if ACTIVATION_CONSTRUCTOR in text:
                    sites.append(ActivationConstructionSite(path=path, line=line_number))
    return sites


def _is_excluded(path: Path, exclude: tuple[Path, ...]) -> bool:
    """Report whether a path is one of, or under, the excluded paths.

    Args:
        path: The file being considered.
        exclude: Excluded files or directories.

    Returns:
        (bool) True when the path is the constructor's definition or data, not a consumer.
    """
    resolved = path.resolve()
    for excluded in exclude:
        target = excluded.resolve()
        if resolved == target or target in resolved.parents:
            return True
    return False
