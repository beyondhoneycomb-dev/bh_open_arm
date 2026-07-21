"""Command-line entry to run the synthetic GIL-load harness and publish its artifact.

One invocation runs all seven conditions unattended (acceptance ①) and writes the
artifact JSON, or refuses it if an acceptance clause is violated. `--quick` runs a
small config suitable for a smoke test; the defaults run the full measurement.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sim.harness.artifact import ArtifactRefusedError, write_artifact
from sim.harness.conditions import MeasurementConfig
from sim.harness.harness import run_harness
from sim.harness.load_profile import LoadProfile

# The default load profile: five 640x480 streams, ~48 KB/frame lossless PNG, ~256 KB
# WS serialization per tick — the condition-4 shape at a representative rig scale. It
# is a starting point a caller overrides on the command line, not a pinned truth.
_DEFAULT_STREAMS = 5
_DEFAULT_WIDTH = 640
_DEFAULT_HEIGHT = 480
_DEFAULT_PNG_BYTES = 48 * 1024
_DEFAULT_SERIALIZE_BYTES = 256 * 1024

# The quick config trades statistical power for speed so the CLI can be exercised in a
# few seconds; the full defaults are what a published PG-RT-001a basis run uses.
_QUICK_CONFIG = MeasurementConfig(
    target_hz=250.0,
    tick_count=200,
    warmup=40,
    self_overhead_iterations=1000,
    sweep_frequencies_hz=(125.0, 250.0),
    sweep_tick_count=150,
    interleave_segment_len=15,
    interleave_repeats=12,
)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        (argparse.ArgumentParser) The configured parser.
    """
    parser = argparse.ArgumentParser(description="Synthetic GIL-load harness (PG-RT-001a basis).")
    parser.add_argument("--out", type=Path, required=True, help="artifact JSON output path")
    parser.add_argument(
        "--streams", type=int, default=_DEFAULT_STREAMS, help="synthetic stream count"
    )
    parser.add_argument("--width", type=int, default=_DEFAULT_WIDTH, help="frame width in pixels")
    parser.add_argument(
        "--height", type=int, default=_DEFAULT_HEIGHT, help="frame height in pixels"
    )
    parser.add_argument(
        "--png-bytes", type=int, default=_DEFAULT_PNG_BYTES, help="PNG write bytes/frame"
    )
    parser.add_argument(
        "--serialize-bytes",
        type=int,
        default=_DEFAULT_SERIALIZE_BYTES,
        help="WS serialization bytes/tick",
    )
    parser.add_argument(
        "--target-hz", type=float, default=None, help="override the measured frequency"
    )
    parser.add_argument("--quick", action="store_true", help="run the small smoke-test config")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the harness from the command line and write its artifact.

    Args:
        argv: Argument vector; `sys.argv[1:]` when None.

    Returns:
        (int) 0 on success, 2 when the artifact was refused (an acceptance violation).
    """
    args = _build_parser().parse_args(argv)
    profile = LoadProfile(
        stream_count=args.streams,
        resolution_width=args.width,
        resolution_height=args.height,
        png_write_bytes_per_frame=args.png_bytes,
        serialize_bytes_per_tick=args.serialize_bytes,
    )
    config = _QUICK_CONFIG if args.quick else MeasurementConfig()
    if args.target_hz is not None:
        from dataclasses import replace

        config = replace(config, target_hz=args.target_hz)

    result = run_harness(profile, config)
    try:
        artifact = write_artifact(result, args.out)
    except ArtifactRefusedError as refused:
        print(f"artifact refused: {refused}", file=sys.stderr)
        return 2

    contribution = artifact["gil_contribution"]["gil_contribution_sec"]
    distinguishable = artifact["load_distinguishability"]["distinguishable"]
    print(f"wrote {args.out}")
    print(f"  load bites (condition 4 vs 1 distinguishable): {distinguishable}")
    print(f"  GIL contribution (condition 4 - 5): {contribution * 1e6:.1f} us")
    print(f"  connect() call count: {artifact['connect_call_count']}")
    print(f"  f_max_python (provisional): {artifact['fmax_python_provisional']['value_hz']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
