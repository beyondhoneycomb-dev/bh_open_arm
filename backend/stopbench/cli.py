"""Run the offline WP-2A-06 stop-path decomposition over a capture file, and print it.

This is the on-host entry point for the parts of WP-2A-06 that run without a rig: it reads
one capture in the same schema the re-verification hook consumes, assembles the evidence
offline (`basis="synthetic-timestamps"` unless the file declares otherwise), and prints it.
It renders no verdict — the numeric target stays `[unconfirmed]` — and it inherits every
refusal of the bench: a stop path holding `disable_torque` or a capture with an untrusted
clock exits non-zero rather than printing a green-looking artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.stopbench.bench import SYNTHETIC_BASIS, build_stop_path_regression_artifact
from backend.stopbench.precondition import DisableTorqueOnStopPathError
from backend.stopbench.reverify import parse_capture
from backend.torque_bringup import StopLatencyArtifactRefusedError


def main(argv: list[str] | None = None) -> int:
    """Assemble and print the offline stop-path decomposition for one capture file.

    Args:
        argv: Command-line arguments, or None to read `sys.argv`.

    Returns:
        (int) 0 on success; 1 when a precondition refuses the artifact.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="capture JSON: samples + clock_provenance")
    parser.add_argument(
        "--basis",
        default=SYNTHETIC_BASIS,
        help="artifact basis label (default: synthetic-timestamps)",
    )
    args = parser.parse_args(argv)

    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    samples, clock_provenance = parse_capture(capture)
    try:
        artifact = build_stop_path_regression_artifact(
            samples=samples,
            clock_provenance=clock_provenance,
            basis=str(args.basis),
        )
    except (DisableTorqueOnStopPathError, StopLatencyArtifactRefusedError) as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 1

    print(json.dumps(artifact, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
