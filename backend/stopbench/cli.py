"""Print the WP-2A-06 stop-path evidence: the declared shape and the static check.

The on-host entry point for the whole of WP-2A-06 — there is no rig stage. It takes no
capture file, because no stop-path timing is captured (`03` §5.7.0 cannot be satisfied on
this rig), and it inherits every refusal of the bench: a stop path holding `disable_torque`
or a stage anchor that no longer resolves exits non-zero rather than printing an artifact.
"""

from __future__ import annotations

import argparse
import json
import sys

from backend.stopbench.bench import build_stop_path_artifact
from backend.stopbench.path import StopPathAnchorMissingError
from backend.stopbench.precondition import (
    DisableTorqueOnStopPathError,
    StopPathScanEmptyError,
)


def main(argv: list[str] | None = None) -> int:
    """Assemble and print the stop-path evidence.

    Args:
        argv: Command-line arguments, or None to read `sys.argv`.

    Returns:
        (int) 0 on success; 1 when a refusal blocks the artifact.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    try:
        artifact = build_stop_path_artifact()
    except (
        DisableTorqueOnStopPathError,
        StopPathAnchorMissingError,
        StopPathScanEmptyError,
    ) as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 1

    print(json.dumps(artifact, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
