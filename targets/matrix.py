"""Load and validate the deploy-target matrix (WP-ENV-02 acceptance ①–③).

Stdlib + pyyaml only, so the light lane can validate the matrix without the robot
stack. Validation is three claims:

  ① every one of the four fleet targets is present, each either RESOLVED or carrying
    an explicit deferral reason — a target with neither is a silent failure;
  ② A100 and H100 are present as explicit exclusions with an Isaac/RT-core reason;
  ③ every blocked_path names a guard predicate that resolves to a real callable in
    `targets.guards`.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

MATRIX_PATH = Path(__file__).resolve().parent / "matrix.yaml"

FLEET_TARGETS = ("jetson_nano", "jetson_orin", "rtx_5090", "rtx_a6000")
EXCLUDED_TARGETS = ("a100", "h100")

STATUS_RESOLVED = "RESOLVED"
STATUS_DEFERRED = "DEFERRED"
_VALID_STATUS = frozenset({STATUS_RESOLVED, STATUS_DEFERRED})

_TARGET_FIELDS = ("target_id", "arch", "accel", "python_abi", "supported_profiles", "blocked_paths")


@dataclass(frozen=True)
class MatrixReport:
    """The verdict of validating the matrix.

    Attributes:
        ok: True when every claim holds.
        problems: One line per defect; empty when `ok`.
    """

    ok: bool
    problems: tuple[str, ...]


def load_matrix(path: Path = MATRIX_PATH) -> dict[str, Any]:
    """Parse the matrix document.

    Args:
        path: Path to `targets/matrix.yaml`.

    Returns:
        (dict[str, Any]) The parsed mapping.

    Raises:
        TypeError: When the document does not parse to a mapping.
    """
    loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} did not parse to a mapping")
    return loaded


def _guard_resolves(dotted: str) -> bool:
    """Report whether a dotted name resolves to a callable guard.

    Args:
        dotted: `module.attr` path, e.g. `targets.guards.sync_over_inference_ceiling`.

    Returns:
        (bool) True when the attribute exists and is callable.
    """
    module_name, _, attr = dotted.rpartition(".")
    if not module_name:
        return False
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return False
    return callable(getattr(module, attr, None))


def _validate_target(target: dict[str, Any]) -> list[str]:
    """Validate one fleet-target row.

    Args:
        target: A `targets[]` entry.

    Returns:
        (list[str]) Defect lines for this target.
    """
    problems: list[str] = []
    target_id = str(target.get("target_id", "?"))

    for key in _TARGET_FIELDS:
        if key not in target:
            problems.append(f"{target_id}: missing field {key}")

    resolution = target.get("lock_resolution") or {}
    status = str(resolution.get("status", ""))
    if status not in _VALID_STATUS:
        problems.append(f"{target_id}: lock_resolution.status must be RESOLVED or DEFERRED")
    # Acceptance ①: a deferred target must SAY why; silence is the failure mode.
    if status == STATUS_DEFERRED and not str(resolution.get("reason", "")).strip():
        problems.append(f"{target_id}: DEFERRED without an explicit reason (silent failure)")

    # Acceptance ③: every blocked path names an executable guard predicate.
    for blocked in target.get("blocked_paths") or []:
        predicate = str(blocked.get("predicate", ""))
        if not _guard_resolves(predicate):
            problems.append(
                f"{target_id}: blocked_path {blocked.get('name', '?')!r} "
                f"predicate {predicate!r} does not resolve to a callable guard"
            )
    return problems


def validate_matrix(document: dict[str, Any]) -> MatrixReport:
    """Validate the full matrix against WP-ENV-02 acceptance ①–③.

    Args:
        document: The parsed matrix mapping.

    Returns:
        (MatrixReport) Verdict with per-defect problem lines.
    """
    problems: list[str] = []
    targets = {str(t.get("target_id", "")): t for t in (document.get("targets") or [])}

    # ① all four fleet targets present and each resolved-or-deferred.
    for target_id in FLEET_TARGETS:
        if target_id not in targets:
            problems.append(f"missing fleet target: {target_id}")
    for target in targets.values():
        problems.extend(_validate_target(target))

    # ② A100/H100 present as explicit exclusions with a reason.
    excluded = {str(e.get("target_id", "")): e for e in (document.get("excluded") or [])}
    for target_id in EXCLUDED_TARGETS:
        entry = excluded.get(target_id)
        if entry is None:
            problems.append(f"missing explicit exclusion: {target_id}")
        elif not str(entry.get("reason", "")).strip():
            problems.append(f"exclusion {target_id} has no reason")

    return MatrixReport(ok=not problems, problems=tuple(problems))
