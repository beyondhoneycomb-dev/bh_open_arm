"""Parser for the M-1 harness tool (`motor_sampling_check --all <hz> <if> -fd`) output.

`15` §2.10 M-1 runs the existing `motor_sampling_check` tool across a frequency
sweep; its built-in output carries Target Hz / Actual Hz / RTT(µs) / per-motor
temperature, and the plan's ~20-line tool modification adds the per-cycle
`recv_all` consumed-frame count and per-motor state-update interval (NFR-PRF-046).
This module turns one run's stdout into structured samples that feed the
distribution computer (RTT), the `f_max_can` computer (target/actual), and the
frames-per-cycle recorder (consumed frames).

Deferral boundary: the tool binary and the real adapter do not exist on this host,
so the *values* are produced elsewhere. The tool's exact stdout format is likewise
unconfirmed here; this parser reads a documented line grammar and the
re-verification hook (`reverify.py`) re-runs it against a real captured log the
moment one is supplied. The grammar it expects, per run:

    target_hz=<int>
    cycle=<int> rtt_us=<float> frames=<int> [actual_hz=<float>]   (repeated)
    actual_hz=<float>                                             (run summary)

Lines it does not recognise are ignored, so a real log with extra banner lines
parses without special-casing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TARGET_HZ = re.compile(r"\btarget_hz\s*=\s*(\d+)")
_ACTUAL_HZ = re.compile(r"\bactual_hz\s*=\s*([\d.]+)")
_CYCLE = re.compile(
    r"\bcycle\s*=\s*(?P<cycle>\d+)\s+rtt_us\s*=\s*(?P<rtt>[\d.]+)\s+frames\s*=\s*(?P<frames>\d+)"
)


@dataclass
class SweepRunSamples:
    """The parsed samples of one sweep run at one target frequency.

    Attributes:
        target_hz: The commanded frequency this run swept.
        actual_hz: The run's achieved frequency (the summary value, or the last
            per-cycle value seen), or None when the run reported none.
        rtt_us: Per-cycle RTT samples, in microseconds, in cycle order.
        frames_per_cycle: Per-cycle consumed-frame counts, in cycle order.
    """

    target_hz: int
    actual_hz: float | None = None
    rtt_us: list[float] = field(default_factory=list)
    frames_per_cycle: list[int] = field(default_factory=list)


def parse_run(tool_output: str) -> SweepRunSamples:
    """Parse one `motor_sampling_check` run's stdout into structured samples.

    The run summary `actual_hz=` (a bare line, not on a cycle line) wins over any
    per-cycle `actual_hz`, since the tool's verdict is on the summary figure. When
    no summary line is present the last per-cycle value is used as a fallback.

    Args:
        tool_output: One run's captured stdout.

    Returns:
        (SweepRunSamples) The run's target, achieved rate, RTT and frame samples.

    Raises:
        ValueError: If no `target_hz=` line is present — the run is unidentifiable.
    """
    target_match = _TARGET_HZ.search(tool_output)
    if target_match is None:
        raise ValueError("no target_hz= line found; run is unidentifiable")

    run = SweepRunSamples(target_hz=int(target_match.group(1)))
    last_cycle_actual: float | None = None
    for line in tool_output.splitlines():
        cycle_match = _CYCLE.search(line)
        if cycle_match:
            run.rtt_us.append(float(cycle_match.group("rtt")))
            run.frames_per_cycle.append(int(cycle_match.group("frames")))
            actual_on_cycle = _ACTUAL_HZ.search(line)
            if actual_on_cycle:
                last_cycle_actual = float(actual_on_cycle.group(1))
            continue
        # Any non-cycle line carrying actual_hz is a run summary; the last one wins.
        # The `target_hz=` line has no actual_hz and is skipped here on that basis,
        # so a summary line may legitimately also print the target.
        summary = _ACTUAL_HZ.search(line)
        if summary:
            run.actual_hz = float(summary.group(1))
    if run.actual_hz is None:
        run.actual_hz = last_cycle_actual
    return run


def parse_sweep(runs_output: dict[int, str]) -> list[SweepRunSamples]:
    """Parse a whole frequency sweep: one tool run per target frequency.

    Args:
        runs_output: target_hz -> that run's captured stdout.

    Returns:
        (list[SweepRunSamples]) One parsed run per target, ascending by target.
    """
    return [parse_run(runs_output[target]) for target in sorted(runs_output)]
