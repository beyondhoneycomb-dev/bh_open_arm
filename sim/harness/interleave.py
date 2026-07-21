"""Interleaved measurement — the drift-robust basis for "load bites" and GIL contribution.

Two separate victim runs cannot be compared cleanly: a busy machine's cycle-time
distribution drifts between runs (frequency scaling, thermal, co-tenants), and a rank
test would read that drift as a difference, so a no-load run could look
"distinguishable" from idle purely by drift. That would make the acceptance ③
anti-rig property unreliable and the GIL-contribution number (acceptance ④) partly
drift.

The fix is to interleave. One continuous victim loop runs while the load is gated
through three states in short, repeated segments — OFF, same-process, separate-process
— tagging each cycle with the state it ran under. Because the states alternate on a
sub-100 ms cadence, machine drift is shared across all three, so the differences
between the tagged distributions are the load's doing, not the clock's:

  * same-process vs OFF is the proof the load bites (③).
  * same-process vs separate-process is the GIL contribution: identical work, the only
    difference being whose GIL it contends for (④).

The load worker runs the whole time; a per-state active flag gates whether it does
work (contending for a GIL) or yields. A no-load profile never contends in any state,
so all three distributions coincide and nothing is distinguishable — exactly what a
no-load harness must show.
"""

from __future__ import annotations

import multiprocessing as mp
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from multiprocessing.synchronize import Event as MpEvent

from sim.harness.control_loop import DummyBinding, PayloadKind, make_payload
from sim.harness.gil_load import run_load
from sim.harness.histogram import CycleTimeHistogram
from sim.harness.load_profile import LoadProfile
from sim.harness.statistics import DistributionComparison, compare_distributions

_SEGMENT_OFF = "off"
_SEGMENT_SAME = "same"
_SEGMENT_SEP = "sep"
_SEGMENT_ORDER = (_SEGMENT_OFF, _SEGMENT_SAME, _SEGMENT_SEP)

# Workers must drain shortly after being asked to stop; past this the separate-process
# worker is terminated so the interleaved run can never hang.
_JOIN_TIMEOUT_SEC = 5.0


@dataclass
class InterleavedMeasurement:
    """The three tagged distributions and the two drift-robust comparisons.

    Attributes:
        off: Cycle times with the load OFF (idle) — condition 1.
        same_process: Cycle times with the load in the same process — condition 4.
        separate_process: Cycle times with the load in a separate process — condition 5.
        load_bite: same-process vs off — proof the load bites (③).
        gil_contribution: same-process vs separate-process — the GIL contribution (④).
    """

    off: CycleTimeHistogram
    same_process: CycleTimeHistogram
    separate_process: CycleTimeHistogram
    load_bite: DistributionComparison
    gil_contribution: DistributionComparison


def _run_segment(
    period: float,
    length: int,
    payload: object,
) -> np.ndarray:
    """Run one interleaved segment and return its per-cycle times.

    The first cycle of a segment straddles the load-state transition, so the caller
    drops it; this returns all `length` cycles and lets the caller trim.

    Args:
        period: The target cycle period in seconds.
        length: How many cycles to run in the segment.
        payload: The per-tick control payload (a callable).

    Returns:
        (np.ndarray) `length` cycle times in seconds.
    """
    perf_counter = time.perf_counter
    sleep = time.sleep
    run = payload  # a zero-arg callable
    starts = np.empty(length + 1, dtype=np.float64)
    for index in range(length + 1):
        start = perf_counter()
        starts[index] = start
        run()  # type: ignore[operator]
        remaining = period - (perf_counter() - start)
        if remaining > 0.0:
            sleep(remaining)
    return np.diff(starts)


def run_interleaved(
    profile: LoadProfile,
    target_hz: float,
    warmup: int,
    segment_len: int,
    repeats: int,
    dataset_dir: str,
) -> InterleavedMeasurement:
    """Run the interleaved OFF/same/separate measurement and compare the three states.

    Args:
        profile: The four-parameter load profile.
        target_hz: The victim loop frequency.
        warmup: Settling cycles to run and discard before the segments begin.
        segment_len: Cycles per segment (its first cycle is dropped as a transition).
        repeats: How many OFF/same/separate rounds to run.
        dataset_dir: Directory the two load workers write under.

    Returns:
        (InterleavedMeasurement) The three tagged distributions and the two
        drift-robust comparisons.
    """
    period = 1.0 / target_hz
    same_dir = str(Path(dataset_dir) / "same")
    sep_dir = str(Path(dataset_dir) / "sep")

    stop = threading.Event()
    thread_active = threading.Event()
    thread = threading.Thread(
        target=run_load,
        args=(profile, stop, same_dir, thread_active),
        name="interleave-same-process-load",
        daemon=True,
    )

    context = mp.get_context("fork")
    proc_stop = context.Event()
    proc_active = context.Event()
    process = context.Process(
        target=run_load,
        args=(profile, proc_stop, sep_dir, proc_active),
        name="interleave-separate-process-load",
        daemon=True,
    )

    buckets: dict[str, list[float]] = {segment: [] for segment in _SEGMENT_ORDER}

    # Fork the separate-process worker while this process is still single-threaded,
    # before the same-process load thread and the lerobot-importing binding exist, so
    # the child never inherits a lock held by another thread (fork-safety).
    process.start()
    binding = DummyBinding()
    payload = make_payload(PayloadKind.IDLE, binding)
    thread.start()
    try:
        _run_segment(period, warmup, payload)  # discard settling cycles
        for _ in range(repeats):
            for segment in _SEGMENT_ORDER:
                _set_state(thread_active, proc_active, segment)
                cycles = _run_segment(period, segment_len, payload)
                buckets[segment].extend(cycles[1:].tolist())  # drop the transition cycle
    finally:
        stop.set()
        proc_stop.set()
        thread.join(timeout=_JOIN_TIMEOUT_SEC)
        process.join(timeout=_JOIN_TIMEOUT_SEC)
        if process.is_alive():
            process.terminate()
            process.join(timeout=_JOIN_TIMEOUT_SEC)

    off = CycleTimeHistogram(np.array(buckets[_SEGMENT_OFF], dtype=np.float64))
    same = CycleTimeHistogram(np.array(buckets[_SEGMENT_SAME], dtype=np.float64))
    sep = CycleTimeHistogram(np.array(buckets[_SEGMENT_SEP], dtype=np.float64))

    return InterleavedMeasurement(
        off=off,
        same_process=same,
        separate_process=sep,
        load_bite=compare_distributions(same.samples, off.samples),
        gil_contribution=compare_distributions(same.samples, sep.samples),
    )


def _set_state(
    thread_active: threading.Event,
    proc_active: MpEvent,
    segment: str,
) -> None:
    """Gate the two load workers for the current segment state.

    Args:
        thread_active: The same-process worker's active gate.
        proc_active: The separate-process worker's active gate.
        segment: The current segment state.
    """
    if segment == _SEGMENT_SAME:
        thread_active.set()
        proc_active.clear()
    elif segment == _SEGMENT_SEP:
        thread_active.clear()
        proc_active.set()
    else:
        thread_active.clear()
        proc_active.clear()
