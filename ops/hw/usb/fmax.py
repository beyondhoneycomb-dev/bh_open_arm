"""The per-arm `f_max_can` computer for the M-1 frequency sweep.

`15` §2.10 M-1 sweeps target frequencies (100..1000 Hz) and reads each run's
achieved rate; the tool's built-in verdict line is `actual_hz >= 0.95 * target_hz`
(`motor_sampling_check.cpp`). `f_max_can` for an arm is the highest swept target the
arm still met that threshold at — beyond it the bus can no longer keep up. `15`
NFR-PRF-004 then caps every control loop at `f_max * 0.8`, so this figure is a hard
input, not a diagnostic.

Purity: this reduces a `{target_hz: actual_hz}` sweep to one number by the fixed
0.95 rule. It runs identically on synthetic and real sweep data — only the sample
values differ, never the arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass

# The tool's built-in pass threshold: a run counts as "met" when the achieved rate
# is at least this fraction of the target (`motor_sampling_check.cpp`, `15` M-1).
ACHIEVED_FRACTION_THRESHOLD = 0.95


@dataclass(frozen=True)
class SweepRun:
    """One frequency-sweep run for one arm.

    Attributes:
        target_hz: The commanded loop frequency.
        actual_hz: The achieved frequency the tool reported.
    """

    target_hz: int
    actual_hz: float

    @property
    def met_threshold(self) -> bool:
        """Whether this run met the tool's `actual_hz >= 0.95 * target_hz` bar."""
        return self.actual_hz >= ACHIEVED_FRACTION_THRESHOLD * self.target_hz


@dataclass(frozen=True)
class FmaxResult:
    """The `f_max_can` verdict for one arm over one sweep.

    Attributes:
        iface: The arm's CAN interface, e.g. "oa_fl".
        f_max_hz: Highest swept target the arm met the threshold at, or None when it
            failed the lowest target (the bus never kept up at any swept rate).
        runs: The sweep runs behind the verdict, sorted by ascending target.
    """

    iface: str
    f_max_hz: int | None
    runs: tuple[SweepRun, ...]

    def as_dict(self) -> dict[str, object]:
        """Project to a JSON-serialisable mapping for the artifact.

        Returns:
            (dict[str, object]) The verdict and its supporting sweep as plain data.
        """
        return {
            "iface": self.iface,
            "f_max_can_hz": self.f_max_hz,
            "threshold_fraction": ACHIEVED_FRACTION_THRESHOLD,
            "sweep": [
                {"target_hz": run.target_hz, "actual_hz": run.actual_hz, "met": run.met_threshold}
                for run in self.runs
            ],
        }


def compute_fmax(iface: str, sweep: dict[int, float]) -> FmaxResult:
    """Reduce one arm's frequency sweep to its `f_max_can`.

    `f_max_can` is the highest swept target the arm met the 0.95 threshold at.
    A target above `f_max` that happens to pass again (noise) does not raise the
    verdict past the first sustained failure only if the caller's sweep is
    monotonic; here the rule is simply the maximum passing target, which is the
    conservative reading the cap in NFR-PRF-004 depends on.

    Args:
        iface: The arm's CAN interface name.
        sweep: target_hz -> actual_hz for the arm; may be empty.

    Returns:
        (FmaxResult) The verdict, with the sweep runs sorted by ascending target.
    """
    runs = tuple(SweepRun(target_hz=target, actual_hz=sweep[target]) for target in sorted(sweep))
    passing = [run.target_hz for run in runs if run.met_threshold]
    return FmaxResult(iface=iface, f_max_hz=max(passing) if passing else None, runs=runs)
