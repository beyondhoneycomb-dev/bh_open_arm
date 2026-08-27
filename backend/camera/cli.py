"""Run the `PG-CAM-001` capture over this rig's registered cameras and judge it.

`03` §5.9 makes this a repeatable job rather than a one-off: the gate goes `SUPERSEDED` on a
camera-set change, a rig-profile change or a USB topology change. What lives here is the slot
*profile* — the stream each slot is opened at, which is a property of the slot's job. Which
camera is behind a slot is not: it is read from the operator's persisted identification and
resolved against the nodes present at this run (`backend.camera.rig`), because a port path
written into source is an answer that was true when someone typed it and nothing checks it
since. The nodes renumber across reboots (this bench has had the ZED-M and an Arducam swap
numbers while both ports stayed put), and the wrist pair reports one serial between the two of
them, which `portpath` explains at length.

The judging is separated from the capturing on purpose. `run_capture` records what arrived and
`droprate`/`syncslop` compute; this module only compares those numbers against the bars `03` §5.9
fixes, and `capture_verdict` takes them as arguments so every branch of the verdict is driven
without a camera.

**The drop this reports is the device's, not the loop's.** Measured over ten minutes: all three
cameras recorded exactly 17718 frames of 18001 expected, because the runner polls every slot once
per fixed-order pass and the pass rate is the slowest slot's — the count-based figure reports all
three at the worst one's number. Their own buffer timestamps disagreed (247, 255 and 280 skipped
frames), and that is the part belonging to each camera.

**One bar is the same number as its own physical maximum**, and the verdict says so when it is
breached. `NFR-CAM-002` sets the pair spread at q99 ≤ 16.7 ms; `03` §5.9 fixes two cameras with no
hardware sync at up to half a frame apart, which at 30 fps is 16.7 ms. Two cameras whose rates
differ sweep the whole range — the ZED-M runs 33.374 ms against the Arducams' 33.406 ms, a phase
lap every ~35 s — so a long enough run drives q99 to the ceiling by construction. A breach here is
not evidence of a fault, and reporting it without that sentence sends the next person hunting one.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.camera.capture_run import run_capture
from backend.camera.controls import WRIST_CAMERA_CONTROLS
from backend.camera.droprate import expected_frame_count, skipped_frames_from_timestamps
from backend.camera.portpath import CaptureNode, enumerate_capture_nodes
from backend.camera.rig import (
    CameraBindingError,
    SlotProfile,
    binding_path,
    load_binding,
    resolve_slots,
)
from backend.camera.syncslop import build_slop_reports
from backend.camera.v4l2_source import (
    CaptureFormat,
    V4l2FrameSource,
    drain_stale_frames,
    open_frame_source,
)
from backend.config.store import default_config_directory

# The window `PG-CAM-001` ④ asks for: ten continuous minutes.
ACCEPTANCE_DURATION_S = 600.0

TARGET_FPS = 30.0

# `03` §5.9 PASS row: drop ≤ 2%, achieved fps ≥ target × 0.95, pair q99 ≤ 16.7 ms. Spelled as
# named constants so a run reports which bar it was judged against rather than a bare verdict.
DROP_LIMIT_FRACTION = 0.02
ACHIEVED_FPS_FLOOR = 0.95
SLOP_LIMIT_MS = 16.7

WRIST_FORMAT = CaptureFormat(width=1920, height=1200, fps=30)
STEREO_FORMAT = CaptureFormat(width=2560, height=720, fps=30)


# This rig's slots and how each is opened. No port here: which camera answers for a slot is the
# operator's identification, read from `camera_binding.json` at every run.
RIG_SLOTS: Mapping[str, SlotProfile] = {
    "wrist_left": SlotProfile(WRIST_FORMAT, WRIST_CAMERA_CONTROLS),
    "wrist_right": SlotProfile(WRIST_FORMAT, WRIST_CAMERA_CONTROLS),
    # Nothing declared. Its control ranges are unmeasured here and `v4l2-ctl`, which is how a
    # range is read, is not installed on this rig — a declared gain of 200 clamped silently to 8
    # and the readback check refused the camera. Exposure does not enter arrival times or counts.
    "scene_stereo": SlotProfile(STEREO_FORMAT, ()),
}


@dataclass(frozen=True)
class SlotOutcome:
    """What one camera did over the window.

    Attributes:
        slot: The slot key.
        target_fps: The rate its profile asked for.
        received: Frames the runner recorded.
        expected: `round(target_fps × duration)`.
        device_skips: Frames the device itself never delivered, counted from the gaps in its own
            buffer timestamps. This is the per-camera figure; `received` is tied across slots by
            the runner's single-pass loop.
        achieved_fps: Frames recorded per second of window.
    """

    slot: str
    target_fps: float
    received: int
    expected: int
    device_skips: int
    achieved_fps: float

    @property
    def device_drop_fraction(self) -> float:
        """The share of expected frames this camera itself did not deliver."""
        if self.expected <= 0:
            return 0.0
        return self.device_skips / self.expected


@dataclass(frozen=True)
class CaptureVerdict:
    """Whether the run met `PG-CAM-001`, and every bar it missed.

    Attributes:
        passed: True when nothing was breached and the run measured what the gate asks for.
        failures: One line per breach, naming the slot or pair and both numbers.
        slots: Per-camera outcomes.
        pair_q99_ms: Measured pair spreads.
        duration_s: The window actually covered.
    """

    passed: bool
    failures: tuple[str, ...]
    slots: tuple[SlotOutcome, ...]
    pair_q99_ms: Mapping[tuple[str, str], float]
    duration_s: float

    def to_document(self) -> dict[str, Any]:
        """Render the verdict as JSON a later run can be compared against.

        The bars travel with the numbers. A re-run after a rig change is only comparable to this
        one if both say what they were judged against, and `03` §5.9's own PASS row is the thing
        most likely to move between them.
        """
        return {
            "passed": self.passed,
            "duration_s": self.duration_s,
            "failures": list(self.failures),
            "bars": {
                "drop_fraction": DROP_LIMIT_FRACTION,
                "achieved_fps_floor": ACHIEVED_FPS_FLOOR,
                "pair_q99_ms": SLOP_LIMIT_MS,
            },
            "slots": [
                {
                    "slot": outcome.slot,
                    "target_fps": outcome.target_fps,
                    "received": outcome.received,
                    "expected": outcome.expected,
                    "device_skips": outcome.device_skips,
                    "device_drop_fraction": outcome.device_drop_fraction,
                    "achieved_fps": outcome.achieved_fps,
                }
                for outcome in self.slots
            ],
            "pairs": [
                {"pair": list(pair), "q99_ms": q99}
                for pair, q99 in sorted(self.pair_q99_ms.items())
            ],
        }


def capture_verdict(
    slots: Sequence[SlotOutcome],
    pair_q99_ms: Mapping[tuple[str, str], float],
    duration_s: float,
) -> CaptureVerdict:
    """Judge one capture against the `03` §5.9 PASS row.

    Args:
        slots: Per-camera outcomes.
        pair_q99_ms: Measured pair spreads, keyed by slot pair.
        duration_s: The window actually covered.

    Returns:
        (CaptureVerdict) The verdict and every breach.
    """
    failures: list[str] = []
    if not slots:
        failures.append("no slot was captured; a run over no camera measures nothing")
    if not pair_q99_ms:
        # Acceptance ③ is a pair measurement. A run that produced no pair cannot answer it, and
        # passing would report the gate met by a run that never took the reading.
        failures.append("no pair spread was measured; acceptance (3) needs at least two slots")

    for outcome in slots:
        if outcome.device_drop_fraction > DROP_LIMIT_FRACTION:
            failures.append(
                f"{outcome.slot}: device drop {outcome.device_drop_fraction * 100:.2f}% "
                f"exceeds {DROP_LIMIT_FRACTION * 100:.2f}% "
                f"({outcome.device_skips} frames the camera did not deliver)"
            )
        floor = outcome.target_fps * ACHIEVED_FPS_FLOOR
        if outcome.achieved_fps < floor:
            failures.append(
                f"{outcome.slot}: achieved fps {outcome.achieved_fps:.2f} is below the "
                f"{floor:.2f} floor (target {outcome.target_fps:.0f} x {ACHIEVED_FPS_FLOOR})"
            )

    for pair, q99 in sorted(pair_q99_ms.items()):
        if q99 > SLOP_LIMIT_MS:
            failures.append(
                f"{pair[0]}/{pair[1]}: pair q99 {q99:.3f} ms exceeds {SLOP_LIMIT_MS} ms. "
                f"That bar is also the physical maximum for this pair — two cameras with no "
                f"hardware sync are at most half a frame apart (16.7 ms at 30 fps, `03` 5.9), "
                f"and a pair whose rates differ sweeps that whole range, so a long enough run "
                f"reaches the ceiling by construction. This is not by itself evidence of a fault"
            )

    return CaptureVerdict(
        passed=not failures,
        failures=tuple(failures),
        slots=tuple(slots),
        pair_q99_ms=dict(pair_q99_ms),
        duration_s=duration_s,
    )


def resolve_rig(nodes: Sequence[CaptureNode] | None = None) -> dict[str, CaptureNode]:
    """Answer which capture node serves each slot, from the operator's persisted identification.

    Args:
        nodes: The capture nodes present, or None to enumerate them now.

    Returns:
        (dict) Slot name to the node to open, for every slot in `RIG_SLOTS`.

    Raises:
        CameraBindingError: If the record is missing or a bound camera is not present.
    """
    present = enumerate_capture_nodes() if nodes is None else nodes
    binding = load_binding(binding_path(default_config_directory()))
    return resolve_slots(binding, tuple(RIG_SLOTS), present)


def _open_rig() -> dict[str, V4l2FrameSource]:
    """Open every registered camera, or refuse.

    Refusing rather than skipping a camera that will not open: `PG-CAM-001` measures this set,
    and a run over two of three answers a question nobody asked. The tolerant path — a dead
    camera warned about and skipped so the arm keeps moving — is `WP-3B-01`'s, in
    `backend/sensing/connect/**`.
    """
    by_slot = resolve_rig()
    opened: dict[str, V4l2FrameSource] = {}
    try:
        for slot, profile in RIG_SLOTS.items():
            node = by_slot[slot]
            opened[slot] = open_frame_source(
                node=node,
                capture_format=profile.capture_format,
                declared_controls=profile.declared_controls,
            )
            print(
                f"{slot:13} {node.card} @ {node.device} ({node.port_path}) "
                f"{profile.capture_format.width}x{profile.capture_format.height}"
                f"@{profile.capture_format.fps} "
                f"skipped_controls={opened[slot].skipped_controls} "
                f"format={opened[slot].pixel_format_finding or 'as declared'}",
                flush=True,
            )
    except BaseException:
        for source in opened.values():
            source.close()
        raise
    return opened


def run_acceptance(duration_s: float, out_dir: Path | None) -> CaptureVerdict:
    """Capture the registered set for `duration_s` and judge it.

    Args:
        duration_s: Window length in seconds.
        out_dir: Where to write the fixture and the verdict, or None to print only.

    Returns:
        (CaptureVerdict) The verdict.
    """
    sources = _open_rig()
    try:
        # After every camera is open, never per camera: one opens in 0.7 s and the ones already
        # open fill their buffers meanwhile, so the first-opened starts the window several frames
        # ahead of the last.
        drain_stale_frames(list(sources.values()))
        print(f"capturing {duration_s:.0f} s ...", flush=True)
        run = run_capture(
            sources=sources,
            target_fps=dict.fromkeys(sources, TARGET_FPS),
            duration_s=duration_s,
            clock=time.perf_counter,
        )
    finally:
        for source in sources.values():
            source.close()

    outcomes = [
        SlotOutcome(
            slot=slot.slot,
            target_fps=slot.target_fps,
            received=slot.received,
            expected=expected_frame_count(slot.target_fps, run.duration_s),
            device_skips=skipped_frames_from_timestamps(slot.capture_ts_ns, slot.target_fps),
            achieved_fps=slot.received / run.duration_s,
        )
        for slot in run.slots
    ]
    pairs = {report.pair: report.q99_ms for report in build_slop_reports(run.capture_ts_document())}
    verdict = capture_verdict(slots=outcomes, pair_q99_ms=pairs, duration_s=run.duration_s)

    if out_dir is not None:
        run.write(out_dir)
        (out_dir / "verdict.json").write_text(
            json.dumps(verdict.to_document(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return verdict


def main(argv: list[str] | None = None) -> int:
    """Run the acceptance capture and print the verdict.

    Args:
        argv: Command-line arguments, or None to read `sys.argv`.

    Returns:
        (int) 0 when every bar was met; 1 on any breach or refusal.
    """
    parser = argparse.ArgumentParser(prog="oa-camcap", description=__doc__)
    parser.add_argument(
        "--seconds",
        type=float,
        default=ACCEPTANCE_DURATION_S,
        help="capture window; the gate asks for ten continuous minutes",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="directory to write capture_ts.json, frames.json and verdict.json into",
    )
    args = parser.parse_args(argv)

    try:
        verdict = run_acceptance(args.seconds, Path(args.out) if args.out else None)
    except CameraBindingError as unbound:
        print(f"REFUSED: {unbound}", file=sys.stderr)
        return 1

    print(f"\nwindow {verdict.duration_s:.2f} s")
    for outcome in verdict.slots:
        print(
            f"  {outcome.slot:13} recv={outcome.received:6} expected={outcome.expected:6} "
            f"device_skips={outcome.device_skips:5} "
            f"device_drop={outcome.device_drop_fraction * 100:5.2f}% "
            f"fps={outcome.achieved_fps:6.2f}"
        )
    for pair, q99 in sorted(verdict.pair_q99_ms.items()):
        print(f"  pair {pair[0]:13}/{pair[1]:13} q99={q99:7.3f} ms")
    for failure in verdict.failures:
        print(f"  BREACH: {failure}", file=sys.stderr)

    print(f"\nVERDICT: {'PASS' if verdict.passed else 'FAIL'}")
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
