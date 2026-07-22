"""Isolate which joint a residual flags — the "which joint" half of acceptance ①.

The momentum observer's residual is per-joint, so a contact shows up as one or more joints whose
`|r_i|` crosses that joint's threshold. This module is only the comparison and the reporting; the
per-joint thresholds are not defined here. They are WP-2C-03's calibrated output (residual
`max + 3*sigma`, torque-ON, human "no-collision" judgement), so the surface takes them as an
argument rather than baking a number this package is not entitled to own. Passing the FR-SAF-020
literature vector is a caller's choice, made with the UI's "literature-derived, not measured"
notice — not a default hidden here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from backend.gmo.constants import GMO_JOINT_COUNT
from backend.gmo.errors import GmoJointCountError


@dataclass(frozen=True)
class Isolation:
    """Which joints a residual flags against a threshold set, and the dominant one.

    Attributes:
        flagged: Zero-based joint indices whose `|r_i|` reached its threshold, ascending.
        dominant: The joint index of largest `|r_i|`, or None when the residual is all-zero.
        residual: The per-joint residual the isolation was read from, Nm.
    """

    flagged: tuple[int, ...]
    dominant: int | None
    residual: tuple[float, ...]

    @property
    def is_contact(self) -> bool:
        """Whether any joint crossed its threshold."""
        return bool(self.flagged)


def isolate_joints(residual: Sequence[float], thresholds: Sequence[float]) -> Isolation:
    """Report which joints the residual flags against per-joint thresholds.

    Args:
        residual: The observer residual `r`, Nm, joint1..joint7 order.
        thresholds: Per-joint detection thresholds, Nm (WP-2C-03's calibrated set, or a caller's
            literature start point). Each must be non-negative.

    Returns:
        (Isolation) The flagged joints, the dominant joint, and the residual read from.

    Raises:
        GmoJointCountError: If either vector is not `GMO_JOINT_COUNT` wide.
    """
    r = _checked(residual, "residual")
    limits = _checked(thresholds, "thresholds")
    magnitude = np.abs(r)
    flagged = tuple(int(index) for index in np.flatnonzero(magnitude >= limits))
    dominant = int(np.argmax(magnitude)) if np.any(magnitude > 0.0) else None
    return Isolation(flagged=flagged, dominant=dominant, residual=tuple(float(v) for v in r))


def _checked(values: Sequence[float], label: str) -> NDArray[np.float64]:
    """Return `values` as a length-`GMO_JOINT_COUNT` array, refusing a wrong width.

    Raises:
        GmoJointCountError: If the vector is not `GMO_JOINT_COUNT` wide.
    """
    vector = np.asarray(values, dtype=np.float64)
    if vector.shape != (GMO_JOINT_COUNT,):
        raise GmoJointCountError(
            f"{label} must have {GMO_JOINT_COUNT} entries, got shape {vector.shape}"
        )
    return vector
