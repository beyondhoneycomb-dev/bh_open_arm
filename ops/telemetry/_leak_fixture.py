"""A subprocess whose RSS either grows unbounded or stays flat — the leak-monitor fixture.

Acceptance ⑥ requires the RSS slope monitor to detect an *artificial* leak. This module is
that artefact: run with `leak`, it appends and touches a fresh block of memory on every step,
so its resident set climbs steadily; run with `steady`, it allocates nothing and its RSS is
flat. The monitor samples the real `/proc/<pid>/status` of this process and must flag the
first and not the second.

Run as `python -m ops.telemetry._leak_fixture {leak|steady}`. It prints `READY <pid>`, then
grows (or does not) on each line it reads from stdin, exiting cleanly on EOF.
"""

from __future__ import annotations

import os
import sys

READY_PREFIX = "READY "
LEAK_MODE = "leak"
STEADY_MODE = "steady"

# Bytes appended per growth step. Large enough that a handful of steps moves RSS by tens of
# MB — a slope orders of magnitude above the leak threshold, so the detection is unambiguous.
STEP_BYTES = 12 * 1024 * 1024
_PAGE = 4096


def main(argv: list[str]) -> int:
    """Run the leak or steady fixture.

    Args:
        argv: `[mode]` where mode is `leak` or `steady`.

    Returns:
        (int) 0 on clean shutdown.
    """
    mode = argv[0] if argv else STEADY_MODE
    ballast: list[bytearray] = []

    sys.stdout.write(f"{READY_PREFIX}{os.getpid()}\n")
    sys.stdout.flush()

    for _line in sys.stdin:
        if mode == LEAK_MODE:
            block = bytearray(STEP_BYTES)
            # Touch every page so the growth is resident, not merely reserved.
            for offset in range(0, len(block), _PAGE):
                block[offset] = 1
            ballast.append(block)
        sys.stdout.write("STEP\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
