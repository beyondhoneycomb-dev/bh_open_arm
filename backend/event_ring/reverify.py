"""Rig re-verification hook for WP-2C-09's hardware-deferred acceptance (plan 02a §4.1).

Two claims cannot be decided on this host: that a *real* collision, captured at the
*real* loop rate, dumps a lossless eight-joint eight-channel window, and that a real
payload change or thermal drift shrinks the residual margin. Both need hardware —
the arm, the CAN bus, an actual event. This module re-runs the exact offline pipeline
(`EventRingBuffer` + `ModelErrorMonitor`) over a captured telemetry stream, so the
moment a real capture exists it is replayed and checked rather than asserted here.

The machinery is not deferred: `reverify_from_fixture` drives real-format captures end
to end, which is what the offline test exercises. Only the hardware bytes are pending.
Called without a capture, the hook raises `HardwareDeferredError` — a deferred item
fails loudly, never masquerading as a green.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.event_ring.errors import HardwareDeferredError
from backend.event_ring.monitor import ModelErrorMonitor
from backend.event_ring.ring import EventRingBuffer
from backend.event_ring.sample import EventChannel, TelemetrySample
from ops.cancel.scheduler import LatchReason

# The environment variable a rig operator points at a directory of capture files.
FIXTURE_ENV_VAR = "OPENARM_EVENTRING_REAL_FIXTURE"

_LATCH_PASS = "PASS"
_LATCH_LATCHED = "LATCHED"


@dataclass(frozen=True)
class ReverifyResult:
    """The outcome of replaying one captured event through the offline pipeline.

    Attributes:
        name: The capture's name, from the file.
        matched: Whether the replay's losslessness and re-identification verdict both
            matched what the capture declared it should show.
        detail: A human-readable account of the comparison.
    """

    name: str
    matched: bool
    detail: str


def fixture_dir_from_env() -> Path | None:
    """Return the rig capture directory named by the environment, if any.

    Returns:
        (Path | None) The directory `OPENARM_EVENTRING_REAL_FIXTURE` points at, or
        None when it is unset — the signal that the hardware check is deferred.
    """
    value = os.environ.get(FIXTURE_ENV_VAR)
    return Path(value) if value else None


def _sample_from(entry: dict[str, Any]) -> TelemetrySample:
    """Build a telemetry sample from one capture stream entry."""
    rows = tuple(tuple(float(cell) for cell in row) for row in entry["rows"])
    return TelemetrySample(at=float(entry["at"]), rows=rows)


def reverify_capture(capture: dict[str, Any]) -> ReverifyResult:
    """Replay one parsed capture and compare its verdict to the capture's expectation.

    Args:
        capture: A parsed capture document (see `reverify_from_fixture` for its shape).

    Returns:
        (ReverifyResult) Whether the replayed losslessness and re-identification
        verdict matched the capture's declared expectation.
    """
    name = str(capture.get("name", "unnamed"))
    monitor_spec = capture["monitor"]
    thresholds = {int(key): float(value) for key, value in monitor_spec["thresholds_nm"].items()}
    joint_indices = tuple(int(index) for index in monitor_spec["joint_indices"])
    monitor = ModelErrorMonitor(
        joint_indices=joint_indices,
        thresholds_nm=thresholds,
        window_len=int(monitor_spec["window_len"]),
        margin_decrease_tolerance_nm=float(monitor_spec["margin_decrease_tolerance_nm"]),
    )
    ring = EventRingBuffer(
        capacity=int(capture["capacity"]),
        pre_event_sec=float(capture["pre_event_sec"]),
        post_event_sec=float(capture["post_event_sec"]),
    )

    event_at = float(capture["event_at"])
    baseline_after = int(monitor_spec["baseline_after"])
    capture_handle = None
    for index, entry in enumerate(capture["stream"]):
        sample = _sample_from(entry)
        ring.record(sample)
        monitor.update(
            residuals_nm=sample.channel(EventChannel.R),
            t_mos_degc=sample.channel(EventChannel.T_MOS),
            t_rotor_degc=sample.channel(EventChannel.T_ROTOR),
        )
        if capture_handle is None and sample.at >= event_at:
            capture_handle = ring.on_safety_event(
                LatchReason(
                    gate_id=f"EVENT_RING_REVERIFY:{name}",
                    previous_state=_LATCH_PASS,
                    new_state=_LATCH_LATCHED,
                    latched_at=event_at,
                )
            )
        if index + 1 == baseline_after:
            monitor.freeze_baseline()

    expect = capture["expect"]
    observed_lossless = capture_handle is not None and capture_handle.dump.lossless
    observed_reidentify = monitor.assess().reidentify_needed
    lossless_ok = observed_lossless == bool(expect["lossless"])
    reidentify_ok = observed_reidentify == bool(expect["reidentify"])
    matched = lossless_ok and reidentify_ok
    detail = (
        f"lossless observed={observed_lossless} expected={expect['lossless']}; "
        f"reidentify observed={observed_reidentify} expected={expect['reidentify']}"
    )
    return ReverifyResult(name=name, matched=matched, detail=detail)


def reverify_from_fixture(fixture_dir: Path | None) -> list[ReverifyResult]:
    """Replay every `*.json` capture in a rig fixture directory.

    Each capture is a JSON document with `capacity`, `pre_event_sec`,
    `post_event_sec`, `event_at`, a `stream` of `{at, rows}` telemetry ticks, a
    `monitor` spec (`joint_indices`, `thresholds_nm`, `window_len`,
    `margin_decrease_tolerance_nm`, `baseline_after`), and an `expect`
    (`lossless`, `reidentify`).

    Args:
        fixture_dir: The rig capture directory, or None when none was supplied.

    Returns:
        (list[ReverifyResult]) One result per capture, in filename order.

    Raises:
        HardwareDeferredError: When `fixture_dir` is None — the check needs real
            hardware bytes and refuses to pass without them.
    """
    if fixture_dir is None:
        raise HardwareDeferredError(
            "WP-2C-09 on-hardware acceptance needs a real event capture at the real "
            f"loop rate; set {FIXTURE_ENV_VAR} to a directory of capture .json files"
        )
    results: list[ReverifyResult] = []
    for path in sorted(fixture_dir.glob("*.json")):
        capture = json.loads(path.read_text(encoding="utf-8"))
        results.append(reverify_capture(capture))
    return results
