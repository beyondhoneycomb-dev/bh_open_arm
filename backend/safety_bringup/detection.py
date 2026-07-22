"""Collision-detection configuration: method, its accel-limit precondition, and what is gone.

Four `12` requirements live here, all offline-checkable:

  * FR-SAF-018 — the detection method is one of MOMENTUM_OBSERVER / TORQUE_RESIDUAL /
    CURRENT_LIMIT / DISABLED, defaulting to MOMENTUM_OBSERVER.
  * FR-SAF-014 — a residual-based method (the momentum observer, the torque residual)
    cannot be activated while the acceleration limit is inactive: without the accel limit
    the residual has spurious content, so enabling residual detection on top of it is
    refused.
  * FR-SAF-012 — the octomap environment-collision pipeline is deprecated. The canonical
    camera config has no depth stream, so the MoveIt sensors_3d input never exists;
    environment collision is MJCF cell geom. The code tree must carry zero octomap symbols.
  * FR-SAF-069 / §2.6 — `friction.yaml` is zero bytes, so the v1 friction values are
    invalid and the momentum-observer collision detection (GMO) stays *inactive* until
    PG-FRIC-001 establishes friction, even though the default method names it.

FR-SAF-015 is the fifth, adjacent fact: the teleop QP-IK path has no pre-collision check,
and the UI must say so; the canonical string lives here for the presence check.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from backend.safety_bringup.constants import (
    OCTOMAP_DEPRECATED_SYMBOLS,
    TELEOP_NO_PRECHECK_UI_STRING,
)


class DetectionMethod(Enum):
    """A collision-detection method (`12` FR-SAF-018), default MOMENTUM_OBSERVER."""

    MOMENTUM_OBSERVER = "MOMENTUM_OBSERVER"
    TORQUE_RESIDUAL = "TORQUE_RESIDUAL"
    CURRENT_LIMIT = "CURRENT_LIMIT"
    DISABLED = "DISABLED"


# The residual-based methods: their signal is a generalised-momentum / torque residual,
# which is only trustworthy when the acceleration limit is active (`12` FR-SAF-014).
# CURRENT_LIMIT reads motor current directly and does not depend on the accel limit.
RESIDUAL_BASED_METHODS = frozenset(
    {DetectionMethod.MOMENTUM_OBSERVER, DetectionMethod.TORQUE_RESIDUAL}
)

DEFAULT_DETECTION_METHOD = DetectionMethod.MOMENTUM_OBSERVER


class ResidualDetectionRefusedError(Exception):
    """Raised when residual-based detection is enabled with the accel limit inactive.

    `12` FR-SAF-014: with no acceleration limit the residual carries content the observer
    would read as a phantom collision, so activation is refused rather than allowed to
    latch spuriously.
    """


def enable_residual_detection(method: DetectionMethod, accel_limit_active: bool) -> None:
    """Admit residual-based detection only when the acceleration limit is active (③).

    Args:
        method: The detection method being activated.
        accel_limit_active: Whether the joint acceleration/jerk limit is active.

    Raises:
        ResidualDetectionRefusedError: If a residual-based method is activated while the
            acceleration limit is inactive (`12` FR-SAF-014).
    """
    if method in RESIDUAL_BASED_METHODS and not accel_limit_active:
        raise ResidualDetectionRefusedError(
            f"{method.value} is residual-based and needs the acceleration limit active; "
            "enabling it with accel limit off is refused (12 FR-SAF-014, acceptance ③)"
        )


def gmo_active_default(friction_yaml_path: Path) -> bool:
    """Whether the momentum-observer collision detection is active by default (⑫).

    GMO consumes friction compensation, and `12` §2.6 leaves `friction.yaml` at zero bytes
    with the v1 values invalid, so until PG-FRIC-001 establishes friction the observer
    stays inactive even though MOMENTUM_OBSERVER is the default *method*. An absent or
    empty file is the un-established state.

    Args:
        friction_yaml_path: Path to the friction descriptor.

    Returns:
        (bool) True only when friction is established (file present and non-empty).
    """
    return friction_yaml_path.is_file() and friction_yaml_path.stat().st_size > 0


@dataclass(frozen=True)
class OctomapReference:
    """One residual octomap symbol found in the code tree (`12` FR-SAF-012).

    Attributes:
        path: The file the symbol was found in.
        line: One-based line number.
        symbol: Which deprecated octomap symbol matched.
    """

    path: Path
    line: int
    symbol: str


def scan_octomap_symbols(
    roots: tuple[Path, ...], exclude: tuple[Path, ...]
) -> list[OctomapReference]:
    """Scan Python sources for deprecated octomap symbols; the count must be zero (⑦).

    `12` FR-SAF-012 deprecates the octomap environment-collision pipeline. This is the
    static proof it left no live references. The excluded roots are the paths that name
    the symbols as data — this package's own constants and checker — so they are not
    counted as live uses, the same way the WP-1-02 0xFE scan excludes the sender-detector.

    Args:
        roots: Directories to scan recursively for `*.py`.
        exclude: Paths (files or directories) whose matches are data, not live uses.

    Returns:
        (list[OctomapReference]) Every live octomap reference found, empty when clean.
    """
    references: list[OctomapReference] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if _is_excluded(path, exclude):
                continue
            for line_number, text in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                for symbol in OCTOMAP_DEPRECATED_SYMBOLS:
                    if symbol in text:
                        references.append(
                            OctomapReference(path=path, line=line_number, symbol=symbol)
                        )
    return references


def _is_excluded(path: Path, exclude: tuple[Path, ...]) -> bool:
    """Report whether a path is one of, or under, the excluded paths.

    Args:
        path: The file being considered.
        exclude: Excluded files or directories.

    Returns:
        (bool) True when the path should not be counted as a live use.
    """
    resolved = path.resolve()
    for excluded in exclude:
        target = excluded.resolve()
        if resolved == target or target in resolved.parents:
            return True
    return False


def teleop_precheck_notice() -> str:
    """The UI notice that the teleop QP-IK path has no pre-collision check (`12` FR-SAF-015).

    Returns:
        (str) The canonical UI string acceptance ⑧ checks for.
    """
    return TELEOP_NO_PRECHECK_UI_STRING


def assert_teleop_notice_present(ui_strings: tuple[str, ...]) -> None:
    """Refuse a teleop UI that omits the no-pre-collision-check notice (`12` FR-SAF-015, ⑧).

    Args:
        ui_strings: The strings the teleop UI declares.

    Raises:
        ValueError: If none of the strings carries the required notice.
    """
    if not any(TELEOP_NO_PRECHECK_UI_STRING in text for text in ui_strings):
        raise ValueError(
            "teleop QP-IK UI declares no 'NO pre-collision check' notice; an operator must "
            "not assume a guard that is not there (12 FR-SAF-015, acceptance ⑧)"
        )
