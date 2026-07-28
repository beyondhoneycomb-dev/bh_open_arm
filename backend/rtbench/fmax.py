"""`f_max = min(f_max_can, f_max_python)` and the `x 0.8` figure derived from it.

`15` NFR-PRF-004 gives the usable ceiling as the minimum of the CAN-bound and
Python-bound maxima, with `f_max x 0.8` as the highest operating target it contemplates.
NORM-008 keeps the arithmetic and drops the enforcement: no frequency is a pass/fail
criterion here, so `f_max x 0.8` is published as a figure a reader judges — against the
real measurement, once M-8 produces one — and nothing in this package refuses a target
for exceeding it.

`f_max_can` is a `WP-0B-06` real-bus measurement and does not exist on this host, so it
is optional: when absent, `f_max` falls back to the Python-bound figure alone and records
that it is awaiting the CAN measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.rtbench.constants import FINAL_GATE, TARGET_FREQ_HEADROOM


@dataclass(frozen=True)
class FMax:
    """The usable maximum control frequency and the inputs it was derived from.

    Attributes:
        f_max_can_hz: The CAN-bound maximum from `WP-0B-06`, or None when its real-bus
            measurement is deferred.
        f_max_python_hz: The provisional Python-bound maximum from the synthetic sweep,
            or None when no swept frequency cleared the budget.
        provisional: Whether any input is provisional (the Python figure always is).
    """

    f_max_can_hz: float | None
    f_max_python_hz: float | None
    provisional: bool

    @property
    def f_max_hz(self) -> float | None:
        """The usable maximum: the minimum of the present bounds.

        Returns:
            (float | None) `min` of the available bounds, or None when neither is
            present.
        """
        present = [
            value for value in (self.f_max_can_hz, self.f_max_python_hz) if value is not None
        ]
        return min(present) if present else None

    @property
    def awaiting(self) -> tuple[str, ...]:
        """The inputs still deferred, so a reader knows the figure is incomplete.

        Returns:
            (tuple[str, ...]) The names of the missing bounds.
        """
        missing: list[str] = []
        if self.f_max_can_hz is None:
            missing.append("f_max_can")
        if self.f_max_python_hz is None:
            missing.append("f_max_python")
        return tuple(missing)

    def max_target_hz(self) -> float | None:
        """`f_max x 0.8` — published for a reader, gating nothing (NORM-008).

        Returns:
            (float | None) `f_max x 0.8`, or None when `f_max` is not yet known.
        """
        f_max = self.f_max_hz
        return f_max * TARGET_FREQ_HEADROOM if f_max is not None else None

    def as_record(self) -> dict[str, Any]:
        """Serialize the figure for the artifact.

        Returns:
            (dict[str, Any]) The two bounds, the derived `f_max`, the `x 0.8` figure
            flagged as no verdict, and — when the CAN bound is deferred — its
            re-derivation trigger.
        """
        record: dict[str, Any] = {
            "f_max_can_hz": self.f_max_can_hz,
            "f_max_python_hz": self.f_max_python_hz,
            "f_max_hz": self.f_max_hz,
            "max_target_hz": self.max_target_hz(),
            "headroom": TARGET_FREQ_HEADROOM,
            "is_verdict": False,
            "provisional": self.provisional,
            "awaiting": list(self.awaiting),
        }
        if self.provisional:
            record["superseded_by"] = FINAL_GATE
        return record


def compute_fmax(f_max_can_hz: float | None, f_max_python_hz: float | None) -> FMax:
    """Combine the CAN-bound and Python-bound maxima into the usable `f_max`.

    Args:
        f_max_can_hz: The `WP-0B-06` CAN-bound maximum, or None when deferred.
        f_max_python_hz: The provisional Python-bound maximum from the synthetic sweep.

    Returns:
        (FMax) The combined figure; provisional whenever the Python bound is present or
        a bound is still deferred (the Python figure is always synthetic).
    """
    provisional = f_max_python_hz is not None or f_max_can_hz is None
    return FMax(
        f_max_can_hz=f_max_can_hz,
        f_max_python_hz=f_max_python_hz,
        provisional=provisional,
    )
