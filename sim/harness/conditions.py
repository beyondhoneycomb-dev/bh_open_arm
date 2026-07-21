"""Conditions 1-7 of `15` §2.10, each auto-runnable with zero manual intervention.

`02a` WP-0C-06 acceptance ① requires every condition to run unattended. Each function
here takes a load profile and a measurement config and returns a `ConditionResult`;
the orchestrator in `harness` calls them in sequence. Conditions map to `15` §2.10 as:

  1. idle — the reference baseline (its PASS carries no information, 03 §5.1).
  2. pattern A — the 16-frame/cycle variant.
  3. full teleop — idle plus a synthetic teleop input pipeline.
  4. GIL load, same process — the canonical contention case (03 §5.1a basis).
  5. process separation — the same load in a separate process; (4) minus (5) is the
     GIL contribution (acceptance ④).
  6. RT promotion — `chrt -f` + `mlockall` before/after, run in an isolated child so
     a successful promotion cannot touch the parent; no-gain is valid (acceptance ⑤).
  7. frame count — synthetic model of frames-per-cycle. Real `candump` frame counting
     and the `PG-CAN-001` verdict are `WP-1-04`, so this slot publishes a clearly
     provisional model, never a fabricated bus measurement (`THE ONE RULE`).
"""

from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from sim.harness.control_loop import (
    DummyBinding,
    PayloadKind,
    make_payload,
    run_control_loop,
)
from sim.harness.gil_load import LoadLocation, LoadRunner
from sim.harness.histogram import CycleTimeHistogram
from sim.harness.interleave import InterleavedMeasurement, run_interleaved
from sim.harness.load_profile import LoadProfile
from sim.harness.rt_promotion import promote_realtime, restore_normal


@dataclass(frozen=True)
class MeasurementConfig:
    """How long and how fast the victim loop runs for each condition.

    Attributes:
        target_hz: The loop frequency each condition measures at.
        tick_count: Measured cycles per condition.
        warmup: Discarded settling cycles before measurement.
        self_overhead_iterations: Bookkeeping samples for the self-overhead measure.
        frames_per_cycle_model: Modelled CAN frames per cycle for pattern B (`15` §2.1).
        pattern_a_frames_per_cycle: Modelled frames per cycle for pattern A.
        sweep_frequencies_hz: The main-path (30-250 Hz) frequencies the f_max sweep
            re-measures overrun at.
        sweep_tick_count: Measured cycles per sweep point (usually below `tick_count`
            since the sweep re-runs the loaded measurement at every frequency).
        overrun_tolerance: Fractional slack above the period before a cycle counts as
            an overrun, absorbing the `time.sleep` oversleep floor (recorded in the
            artifact, never hidden).
        interleave_segment_len: Cycles per interleaved segment (its first cycle is
            dropped as a load-state transition).
        interleave_repeats: OFF/same/separate rounds in the interleaved measurement;
            each state collects about `interleave_segment_len * interleave_repeats`
            cycles.
    """

    target_hz: float = 200.0
    tick_count: int = 1500
    warmup: int = 150
    self_overhead_iterations: int = 5000
    frames_per_cycle_model: int = 32
    pattern_a_frames_per_cycle: int = 16
    sweep_frequencies_hz: tuple[float, ...] = (60.0, 125.0, 250.0)
    sweep_tick_count: int = 400
    overrun_tolerance: float = 0.05
    interleave_segment_len: int = 20
    interleave_repeats: int = 40

    @property
    def period_sec(self) -> float:
        """The target cycle period in seconds."""
        return 1.0 / self.target_hz


@dataclass
class ConditionResult:
    """One condition's outcome.

    Attributes:
        number: The condition number, 1-7.
        key: A stable machine key, e.g. `condition_4_gil_load_same_process`.
        title: A human title.
        is_timing: Whether this condition produced a cycle-time distribution. Only
            condition 7 does not; the artifact guard requires a full histogram for
            every condition that does (acceptance ⑥).
        histogram: The cycle-time distribution, when `is_timing`.
        period_sec: The target period the distribution was collected at.
        extra: Condition-specific fields (frame-count model, RT before/after, etc.).
    """

    number: int
    key: str
    title: str
    is_timing: bool
    histogram: CycleTimeHistogram | None = None
    period_sec: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _measure(
    profile: LoadProfile,
    config: MeasurementConfig,
    location: LoadLocation,
    payload_kind: PayloadKind,
    dataset_dir: str,
) -> CycleTimeHistogram:
    """Run the victim loop under a load location and return its distribution.

    Args:
        profile: The load profile (unused when `location` is NONE).
        config: The measurement config.
        location: Where the synthetic load runs.
        payload_kind: The per-tick control payload.
        dataset_dir: Directory the load writes under.

    Returns:
        (CycleTimeHistogram) The measured cycle-time distribution.
    """
    binding = DummyBinding()
    payload = make_payload(payload_kind, binding)
    with LoadRunner(profile, location, dataset_dir):
        samples = run_control_loop(
            target_hz=config.target_hz,
            tick_count=config.tick_count,
            warmup=config.warmup,
            payload=payload,
        )
    return CycleTimeHistogram(samples)


def run_interleaved_conditions(
    profile: LoadProfile, config: MeasurementConfig, dataset_dir: str
) -> tuple[InterleavedMeasurement, ConditionResult, ConditionResult, ConditionResult]:
    """Run the interleaved measurement and build conditions 1, 4 and 5 from it.

    Conditions 1 (idle), 4 (same-process load) and 5 (separate-process load) share one
    drift-robust interleaved run so their comparison is the load's effect, not machine
    drift.

    Args:
        profile: The four-parameter load profile.
        config: The measurement config.
        dataset_dir: Directory the load workers write under.

    Returns:
        (tuple) The interleaved measurement and the three condition results (1, 4, 5).
    """
    interleaved = run_interleaved(
        profile=profile,
        target_hz=config.target_hz,
        warmup=config.warmup,
        segment_len=config.interleave_segment_len,
        repeats=config.interleave_repeats,
        dataset_dir=dataset_dir,
    )
    condition_1 = ConditionResult(
        number=1,
        key="condition_1_idle",
        title="pure loop (idle) — reference only",
        is_timing=True,
        histogram=interleaved.off,
        period_sec=config.period_sec,
    )
    condition_4 = ConditionResult(
        number=4,
        key="condition_4_gil_load_same_process",
        title="GIL load — 5-stream grab + PNG write + dataset write + WS serialize, same process",
        is_timing=True,
        histogram=interleaved.same_process,
        period_sec=config.period_sec,
        extra={"load_profile": profile.as_record()},
    )
    condition_5 = ConditionResult(
        number=5,
        key="condition_5_process_separation",
        title="process separation — same load, separate process",
        is_timing=True,
        histogram=interleaved.separate_process,
        period_sec=config.period_sec,
        extra={"load_profile": profile.as_record()},
    )
    return interleaved, condition_1, condition_4, condition_5


def loaded_same_process_histogram(
    profile: LoadProfile, config: MeasurementConfig, dataset_dir: str
) -> CycleTimeHistogram:
    """Run a standalone same-process loaded measurement — used by the frequency sweep.

    The sweep measures an absolute per-frequency overrun rate, not a cross-condition
    comparison, so it does not need the interleaved drift correction.

    Args:
        profile: The load profile.
        config: The measurement config (its `target_hz` sets the sweep point).
        dataset_dir: Directory the load writes under.

    Returns:
        (CycleTimeHistogram) The loaded distribution at `config.target_hz`.
    """
    return _measure(profile, config, LoadLocation.SAME_PROCESS, PayloadKind.IDLE, dataset_dir)


def condition_2_pattern_a(
    profile: LoadProfile, config: MeasurementConfig, dataset_dir: str
) -> ConditionResult:
    """Pattern-A variant: the 16-frame/cycle path, no load."""
    histogram = _measure(profile, config, LoadLocation.NONE, PayloadKind.PATTERN_A, dataset_dir)
    return ConditionResult(
        number=2,
        key="condition_2_pattern_a",
        title="pattern A — 16 frames/cycle",
        is_timing=True,
        histogram=histogram,
        period_sec=config.period_sec,
        extra={"frames_per_cycle_model": config.pattern_a_frames_per_cycle},
    )


def condition_3_full_teleop(
    profile: LoadProfile, config: MeasurementConfig, dataset_dir: str
) -> ConditionResult:
    """Full teleop loop: idle plus a synthetic `teleop.get_action()`, no load."""
    histogram = _measure(profile, config, LoadLocation.NONE, PayloadKind.TELEOP, dataset_dir)
    return ConditionResult(
        number=3,
        key="condition_3_full_teleop",
        title="full teleop loop (UDP + One-Euro + IK)",
        is_timing=True,
        histogram=histogram,
        period_sec=config.period_sec,
    )


def _loaded_subprocess_entry(
    profile: LoadProfile,
    config: MeasurementConfig,
    dataset_dir: str,
    apply_rt: bool,
    result_queue: Any,
) -> None:
    """Run one loaded measurement in a child process, optionally under RT.

    A successful RT promotion is confined to this child, so it can never alter the
    parent harness or the test runner. The child measures the same-process loaded
    victim loop and returns its samples plus the real RT outcome.

    Args:
        profile: The load profile.
        config: The measurement config.
        dataset_dir: Directory the load writes under.
        apply_rt: Whether to attempt `chrt -f` + `mlockall` before measuring.
        result_queue: Queue the `(samples, rt_record)` result is put on.
    """
    rt_record: dict[str, Any] | None = None
    if apply_rt:
        rt_record = promote_realtime().as_record()

    binding = DummyBinding()
    payload = make_payload(PayloadKind.IDLE, binding)
    with LoadRunner(profile, LoadLocation.SAME_PROCESS, dataset_dir):
        samples = run_control_loop(
            target_hz=config.target_hz,
            tick_count=config.tick_count,
            warmup=config.warmup,
            payload=payload,
        )

    if apply_rt:
        restore_normal()
    result_queue.put((samples, rt_record))


def _run_loaded_in_child(
    profile: LoadProfile, config: MeasurementConfig, dataset_dir: str, apply_rt: bool
) -> tuple[np.ndarray, dict[str, Any] | None]:
    """Spawn a child to run one loaded measurement and collect its result.

    Args:
        profile: The load profile.
        config: The measurement config.
        dataset_dir: Directory the load writes under.
        apply_rt: Whether the child attempts RT promotion.

    Returns:
        (tuple) The cycle-time samples and the RT outcome record (None when
        `apply_rt` is False).
    """
    context = mp.get_context("fork")
    result_queue = context.Queue()
    process = context.Process(
        target=_loaded_subprocess_entry,
        args=(profile, config, dataset_dir, apply_rt, result_queue),
        name=f"rt-measure-{'on' if apply_rt else 'off'}",
    )
    process.start()
    samples, rt_record = result_queue.get()
    process.join(timeout=_CHILD_JOIN_TIMEOUT_SEC)
    return samples, rt_record


def condition_6_rt_promotion(
    profile: LoadProfile, config: MeasurementConfig, dataset_dir: str
) -> ConditionResult:
    """RT-promotion effectiveness: loaded cycle time before vs after `chrt`+`mlockall`.

    Both measurements run in isolated children under the same load. The gain is the
    median cycle-time reduction; a non-positive gain, and the case where promotion was
    refused for lack of privilege, are both published verbatim (acceptance ⑤). The gain
    is only an RT effect when promotion was actually applied — `gain_interpretable`
    says so, since when RT is refused the before/after differ only by machine drift, not
    scheduling, and that must not be read as an RT benefit.
    """
    before_samples, _ = _run_loaded_in_child(profile, config, dataset_dir, apply_rt=False)
    after_samples, rt_record = _run_loaded_in_child(profile, config, dataset_dir, apply_rt=True)

    before = CycleTimeHistogram(before_samples)
    after = CycleTimeHistogram(after_samples)
    gain_sec = float(np.median(before_samples) - np.median(after_samples))
    applied = bool(rt_record and rt_record.get("applied"))

    return ConditionResult(
        number=6,
        key="condition_6_rt_promotion",
        title="RT promotion — chrt -f + mlockall, before/after",
        is_timing=True,
        histogram=before,
        period_sec=config.period_sec,
        extra={
            "rt_promotion": rt_record,
            "median_gain_sec": gain_sec,
            "gain_is_positive": gain_sec > 0.0,
            "gain_interpretable": applied,
            "gain_note": (
                "gain is an RT effect only when rt_promotion.applied is true; when RT "
                "was refused, before/after differ by machine drift, not scheduling"
            ),
            "before": before.as_record(),
            "after": after.as_record(),
        },
    )


def condition_7_frame_count(config: MeasurementConfig) -> ConditionResult:
    """Frames-per-cycle — a synthetic model, with the real bus count deferred to `WP-1-04`.

    There is no CAN bus in this offline harness, so there is nothing to `candump`. The
    honest slot publishes the modelled pattern-B frames-per-cycle, flagged provisional,
    and states plainly that the `PG-CAN-001` verdict comes from `WP-1-04`'s real
    `candump` — never a fabricated bus measurement.
    """
    return ConditionResult(
        number=7,
        key="condition_7_frame_count",
        title="frame count — synthetic model (real candump is WP-1-04)",
        is_timing=False,
        extra={
            "frames_per_cycle_model": config.frames_per_cycle_model,
            "pattern": "B",
            "provisional": True,
            "source": "synthetic-model",
            "real_measurement_wp": "WP-1-04",
            "canonical_gate": "PG-CAN-001",
            "note": (
                "no CAN bus in the offline harness; this is the modelled frame count, "
                "not a candump measurement — PG-CAN-001 is judged by WP-1-04"
            ),
        },
    )


# A child measurement must have already delivered its samples over the queue before
# this join; the timeout only bounds a pathological non-exit.
_CHILD_JOIN_TIMEOUT_SEC = 30.0
