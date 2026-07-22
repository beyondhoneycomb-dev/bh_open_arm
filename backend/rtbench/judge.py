"""The `PG-RT-001a` verdict: main-path overrun over the 30-250 Hz band, then escalate.

`02a` WP-1-04 acceptance ⑤ fixes both halves of this rule and forbids inventing a
third: a run passes when every main-path frequency clears the 0.1% overrun budget
(`15` NFR-PRF-040), and on failure the retry escalates through an *ordered, frozen*
set of variants — process separation, then pattern A, then RT promotion, then worker
separation — never a variant the plan did not enumerate, and never a CAN-ownership
transfer. The order is forced because `15` NFR-PRF-040 is explicit that in Python
PREEMPT_RT cannot fix GIL contention, so process separation must be tried before RT
promotion.

The judgment basis is the *synthetic* condition-4 load (`WP-0C-06`), which runs on
this host; that is what makes `a` a provisional verdict rather than a final one. Every
verdict here is `provisional` and names `PG-RT-001b` as the gate that supersedes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.rtbench.constants import (
    FINAL_GATE,
    GATE_STATE_PASS,
    GATE_STATE_RETRY_WITH_VARIANT,
    MAIN_PATH_BAND_HIGH_HZ,
    MAIN_PATH_BAND_LOW_HZ,
    MAIN_PATH_OVERRUN_BUDGET,
    PROVISIONAL_GATE,
    SYNTHETIC_BASIS,
)


@dataclass(frozen=True)
class BandPoint:
    """One (frequency, overrun-rate) sample of the main-path sweep.

    Attributes:
        target_hz: The frequency the loaded loop was measured at.
        overrun_rate: Fraction of cycles that missed the period, in `[0, 1]`.
    """

    target_hz: float
    overrun_rate: float

    def in_main_path(self) -> bool:
        """Whether this frequency lies in the 30-250 Hz main-path band.

        Returns:
            (bool) True when the frequency is within the judged band.
        """
        return MAIN_PATH_BAND_LOW_HZ <= self.target_hz <= MAIN_PATH_BAND_HIGH_HZ

    def within_budget(self) -> bool:
        """Whether the overrun rate clears the main-path budget.

        Returns:
            (bool) True when the overrun rate is at or below the 0.1% budget.
        """
        return self.overrun_rate <= MAIN_PATH_OVERRUN_BUDGET

    def as_record(self) -> dict[str, Any]:
        """Serialize the point for the artifact.

        Returns:
            (dict[str, Any]) The frequency, overrun rate, and budget status.
        """
        return {
            "target_hz": self.target_hz,
            "overrun_rate": self.overrun_rate,
            "within_budget": self.within_budget(),
        }


@dataclass(frozen=True)
class Variant:
    """One enumerated retry variant, in the order acceptance ⑤ forces.

    Attributes:
        key: A stable machine key for the variant.
        condition: The `15` §2.10 condition it corresponds to, or empty for the
            terminal worker-separation fallback.
        rationale: Why this variant sits where it does in the forced order.
    """

    key: str
    condition: str
    rationale: str

    def as_record(self) -> dict[str, str]:
        """Serialize the variant for the artifact.

        Returns:
            (dict[str, str]) The variant key, condition, and rationale.
        """
        return {"key": self.key, "condition": self.condition, "rationale": self.rationale}


# `02a` WP-1-04 acceptance ⑤ / `15` NFR-PRF-040. This tuple is the *whole* escalation
# and its order is load-bearing: process separation precedes RT promotion because
# PREEMPT_RT cannot fix GIL contention in Python, and worker separation is the terminal
# fallback — a RETRY_WITH_VARIANT, explicitly not a CAN-ownership transfer. Nothing may
# be added to this tuple; adding a variant is the "invention" the acceptance forbids.
FORCED_VARIANT_ESCALATION: tuple[Variant, ...] = (
    Variant(
        key="process_separation",
        condition="condition_5",
        rationale="move the load off the control process first; GIL contention is the "
        "dominant cost and PREEMPT_RT cannot fix it (15 NFR-PRF-040)",
    ),
    Variant(
        key="pattern_a",
        condition="condition_2",
        rationale="drop to the 16-frame/cycle pattern A path to halve the per-cycle CAN "
        "work when process separation alone does not clear the budget",
    ),
    Variant(
        key="rt_promotion",
        condition="condition_6",
        rationale="apply chrt -f + mlockall last, since RT promotion only helps once GIL "
        "contention has already been removed (15 NFR-PRF-040)",
    ),
    Variant(
        key="worker_separation",
        condition="",
        rationale="terminal fallback: run the control loop in a separated worker "
        "(RETRY_WITH_VARIANT), never a CAN-ownership transfer",
    ),
)


@dataclass(frozen=True)
class PgRt001aVerdict:
    """The provisional `PG-RT-001a` verdict over one measured band.

    Attributes:
        status: `PASS` or `RETRY_WITH_VARIANT`.
        band_points: Every main-path point that was judged.
        failing_points: The main-path points that missed the budget.
        escalation: The forced retry order, empty on `PASS`.
        basis: The measurement basis; always the synthetic GIL load for `a`.
        superseded_by: The gate whose PASS supersedes this verdict.
    """

    status: str
    band_points: tuple[BandPoint, ...]
    failing_points: tuple[BandPoint, ...]
    escalation: tuple[Variant, ...]
    basis: str
    superseded_by: str

    @property
    def passed(self) -> bool:
        """Whether the verdict is a pass.

        Returns:
            (bool) True when the status is `PASS`.
        """
        return self.status == GATE_STATE_PASS

    def as_record(self) -> dict[str, Any]:
        """Serialize the verdict for the artifact.

        Returns:
            (dict[str, Any]) The full verdict, flagged provisional and naming its
            superseding gate; `is_wave1_exit_permit` restates that a `PASS` means
            "proceed until the rig overturns it", not "final".
        """
        return {
            "gate": PROVISIONAL_GATE,
            "status": self.status,
            "provisional": True,
            "is_wave1_exit_permit": self.passed,
            "basis": self.basis,
            "overrun_budget": MAIN_PATH_OVERRUN_BUDGET,
            "band_points": [point.as_record() for point in self.band_points],
            "failing_points": [point.as_record() for point in self.failing_points],
            "escalation": [variant.as_record() for variant in self.escalation],
            "superseded_by": self.superseded_by,
            "note": (
                "provisional synthetic-load verdict; a PASS is a Wave 1 exit permit that "
                "PG-RT-001b (WP-3C-02) can supersede, not a final judgment"
            ),
        }


def judge_pg_rt_001a(band_points: tuple[BandPoint, ...]) -> PgRt001aVerdict:
    """Render the provisional `PG-RT-001a` verdict over a measured band.

    Only main-path points (30-250 Hz) are judged; a point outside the band is carried
    for the record but cannot fail the verdict. A pass requires every main-path point
    to clear the budget. On any failure the verdict is `RETRY_WITH_VARIANT` and carries
    the whole forced escalation — the caller works down it in order, never reordering
    or extending it.

    Args:
        band_points: The (frequency, overrun-rate) sweep over the control band.

    Returns:
        (PgRt001aVerdict) The verdict, always provisional, naming `PG-RT-001b` as its
        superseding gate.
    """
    main_path = tuple(point for point in band_points if point.in_main_path())
    failing = tuple(point for point in main_path if not point.within_budget())
    status = GATE_STATE_PASS if not failing else GATE_STATE_RETRY_WITH_VARIANT
    escalation = () if not failing else FORCED_VARIANT_ESCALATION
    return PgRt001aVerdict(
        status=status,
        band_points=main_path,
        failing_points=failing,
        escalation=escalation,
        basis=SYNTHETIC_BASIS,
        superseded_by=FINAL_GATE,
    )


def band_points_from_sweep(sweep: list[dict[str, Any]]) -> tuple[BandPoint, ...]:
    """Build band points from a `WP-0C-06` frequency-sweep record list.

    Args:
        sweep: The harness `fmax_sweep`, each entry carrying `target_hz` and
            `overrun_rate`.

    Returns:
        (tuple[BandPoint, ...]) One band point per sweep entry, in sweep order.
    """
    return tuple(
        BandPoint(target_hz=float(entry["target_hz"]), overrun_rate=float(entry["overrun_rate"]))
        for entry in sweep
    )
